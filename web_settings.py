import json
import logging
import os
import re
import socket
import subprocess
import tempfile
from flask import Flask, render_template_string, request, jsonify, send_from_directory
from llm_client import OpenAICompatibleClient

app5 = Flask(__name__, static_folder='dist')
logging.getLogger('werkzeug').setLevel(logging.ERROR)
CONFIG_FILE = 'data/db/config.json'
DEFAULT_CONFIG_FILE = 'data/db/config_default.json'


_LLM_PARAMS_DEFAULT = {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.9}
_LLM_PRESET_DEFAULT = "balanced"


def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"加载配置失败，将使用默认配置文件，错误详情: {e}")
        with open(DEFAULT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    
    # P2: 自动补全 LLM 参数字段并立即写回，防止设置页覆盖旧格式
    changed = False
    if 'llm_params' not in cfg:
        cfg['llm_params'] = _LLM_PARAMS_DEFAULT.copy()
        changed = True
    else:
        # 补全缺失的子字段
        for key, val in _LLM_PARAMS_DEFAULT.items():
            if key not in cfg['llm_params']:
                cfg['llm_params'][key] = val
                changed = True
    if 'llm_preset' not in cfg:
        cfg['llm_preset'] = _LLM_PRESET_DEFAULT
        changed = True
    # 向后兼容：TTS 缓存配置
    if 'tts_cache_clean_interval_days' not in cfg:
        cfg['tts_cache_clean_interval_days'] = 7
        changed = True
    if 'tts_cache_session_soft_limit' not in cfg:
        cfg['tts_cache_session_soft_limit'] = 1000
        changed = True
    # 向后兼容：日志配置
    if 'log_path' not in cfg:
        cfg['log_path'] = 'logs'
        changed = True
    if 'log_name' not in cfg:
        cfg['log_name'] = 'run.log'
        changed = True
    # 向后兼容：Qwen3-TTS 配置
    if 'qwentts_model' not in cfg:
        cfg['qwentts_model'] = '/vol1/1000/models/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'
        changed = True
    if 'qwentts_voice' not in cfg:
        cfg['qwentts_voice'] = 'ono_anna'
        changed = True
    if changed:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"自动补全配置写回失败: {e}")
    
    return cfg


def get_llm_params() -> dict:
    """读取 config.json 中的 llm_params（每次调用都读取文件，确保设置页修改后实时生效）"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg.get('llm_params', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_prefer_tts() -> str:
    """实时读取 config.json 中的 prefer_tts（确保设置页修改后无需重启即可生效）"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg.get('prefer_tts', prefer_tts)
    except (FileNotFoundError, json.JSONDecodeError):
        return prefer_tts


def _cast_param_value(key: str, value):
    """将 LLM/VLM 参数字符串值转换为正确的 Python 类型
    
    Args:
        key: 参数名
        value: 原始值
        
    Returns:
        float | int | 原值: 转换后的值
    """
    if key == 'temperature':
        return float(value)
    elif key == 'max_tokens':
        return int(value)
    elif key == 'top_p':
        return float(value)
    return value


def _filter_params(params: dict, engine_name: str, supported_schema: dict) -> dict:
    """根据引擎白名单过滤参数，不支持的参数静默忽略
    
    Args:
        params: 原始参数字典（来自 config.json）
        engine_name: 引擎名称
        supported_schema: 引擎支持的参数名映射 {引擎名: [参数名列表]}
        
    Returns:
        dict: 过滤后的参数，仅包含该引擎支持的键
    """
    allowed = supported_schema.get(engine_name, [])
    filtered = {}
    for k in allowed:
        if k in params:
            filtered[k] = _cast_param_value(k, params[k])
    return filtered


_CONFIG_CACHE: dict = {"mtime": 0, "data": {}}


def get_config() -> dict:
    """实时读取 config.json 完整内容（带 mtime 缓存，同一请求内多次调用只读 1 次文件）

    Returns:
        dict: 配置字典，读取失败时返回空 dict
    """
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
        if mtime != _CONFIG_CACHE["mtime"]:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                _CONFIG_CACHE["data"] = json.load(f)
                _CONFIG_CACHE["mtime"] = mtime
        return _CONFIG_CACHE["data"].copy()
    except (FileNotFoundError, json.JSONDecodeError, PermissionError, OSError) as e:
        logging.getLogger("web_settings").warning(f"get_config 读取失败: {e}, 文件: {os.path.abspath(CONFIG_FILE)}")
        return {}


def get_config_value(key: str, default=None):
    """实时读取 config.json 中的单个配置项

    性能：优先使用 get_config() 的 mtime 缓存，同一请求内无额外文件读取。

    Args:
        key: 配置项键名
        default: 读取失败或键不存在时的默认值

    Returns:
        配置值，或 default
    """
    cfg = get_config()
    if cfg:
        return cfg.get(key, default)
    return default


def get_llm_client(engine_name: str):
    """根据引擎名称和最新配置，动态创建 LLM 客户端

    Args:
        engine_name: LLM 引擎名称

    Returns:
        对应引擎的 API 客户端实例
    """
    cfg = get_config()
    if engine_name == "ZhipuAI":
        from zai import ZhipuAiClient
        return ZhipuAiClient(api_key=cfg.get("glm_key", glm_key))
    elif engine_name == "OpenAI":
        return OpenAICompatibleClient(
            base_url=cfg.get("openai_url", openai_url),
            api_key=cfg.get("openai_key", openai_key)
        )
    elif engine_name == "Ollama":
        return OpenAICompatibleClient(
            base_url=cfg.get("ollama_url", ollama_url),
            api_key="ollama"
        )
    elif engine_name == "LM Studio":
        return OpenAICompatibleClient(
            base_url=cfg.get("lmstudio_url", lmstudio_url),
            api_key="lm-studio"
        )
    else:
        raise ValueError(f"不支持的 LLM 引擎: {engine_name}")


def save_config(config_data):
    """原子写入 config.json，确保任何时刻读取到的都是完整有效的 JSON

    实现：先写入临时文件，再用 os.replace 原子替换目标文件。
    """
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(CONFIG_FILE),
            prefix=os.path.basename(CONFIG_FILE) + ".tmp"
        )
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
        # 清除缓存，确保下次 get_config() 读取最新内容
        _CONFIG_CACHE["mtime"] = 0
        return True
    except Exception as e:
        print(f"保存设置失败，错误详情: {e}")
        return False


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="assets/image/logo.png"/>
    <title>系统设置 - Aivmate LX3</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #001f3f;
            color: white;
            margin: 0;
            padding: 0;
            line-height: 1.6;
            height: 100vh;
            overflow-x: hidden;
        }
        .container {
            width: 99%;
            max-width: 100%;
            min-height: 100vh;
            margin: 0;
            background-color: #003366;
            padding: 20px;
            border-radius: 0;
            box-sizing: border-box;
            box-shadow: none;
        }
        @media screen and (max-width: 768px) {
            .tabs {
                flex-wrap: wrap;
                border-bottom: none;
            }
            .tab {
                flex: 1 1 calc(33.33% - 5px);
                margin-right: 0;
                margin-bottom: 5px;
                text-align: center;
                font-size: 14px;
                padding: 8px 5px;
            }
            .form-group {
                margin-bottom: 12px;
            }
            input, select, textarea {
                font-size: 14px;
                padding: 10px;
            }
            h1 {
                font-size: 1.5rem;
                padding: 10px 0;
                margin-bottom: 15px;
            }
            .section h2 {
                font-size: 1.2rem;
            }
            button {
                width: 100%;
                padding: 12px 0;
                font-size: 16px;
            }
            .notification {
                top: 10px;
                right: 10px;
                left: 10px;
                text-align: center;
                padding: 12px;
            }
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #ffffff;
        }
        .section {
            margin-bottom: 30px;
            padding: 15px;
            background-color: #004080;
            border-radius: 8px;
        }
        .section h2 {
            margin-top: 0;
            color: #66b3ff;
            border-bottom: 1px solid #0066cc;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select, textarea {
            width: 99%;
            padding: 8px;
            background-color: #0055aa;
            border: 1px solid #0077dd;
            border-radius: 4px;
            color: white;
        }
        input[type="number"] {
            width: 100px;
        }
        button {
            background-color: #0077dd;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        }
        button:hover {
            background-color: #0099ff;
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            background-color: #4CAF50;
            color: white;
            border-radius: 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            display: none;
            z-index: 1000;
        }
        .tabs {
            display: flex;
            margin-bottom: 20px;
            border-bottom: 1px solid #0066cc;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            background-color: #004080;
            border: 1px solid #0066cc;
            border-bottom: none;
            border-radius: 5px 5px 0 0;
            margin-right: 5px;
            font-size: 13px;
        }
        .tab.active {
            background-color: #0055aa;
            color: #ffffff;
        }
        .tab-link {
            background-color: #006644;
            color: #ffffff;
        }
        .tab-link:hover {
            background-color: #008866;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        /* ===== 声纹录制区域样式 ===== */
        .voiceprint-record-section {
            margin: 15px 0;
            padding: 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
        }
        .voiceprint-record-section label {
            display: block;
            margin-bottom: 10px;
            font-weight: bold;
            color: #e0e0e0;
        }
        #voiceprint-status {
            margin-bottom: 12px;
            font-size: 14px;
        }
        .collapse-header {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 10px 12px;
            background: rgba(0, 50, 100, 0.3);
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .collapse-header:hover {
            background: rgba(0, 50, 100, 0.5);
        }
        .preset-btn {
            background: rgba(0, 100, 200, 0.2);
            border: 1px solid rgba(0, 150, 255, 0.3);
            color: #a0d0ff;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }
        .preset-btn:hover, .preset-btn.active {
            background: rgba(0, 150, 255, 0.3);
            border-color: rgba(0, 150, 255, 0.6);
            color: #fff;
        }
        input[type="range"] {
            width: 100%;
            accent-color: #4fc3f7;
        }
        #vp-status-text {
            color: #ff9800;
            font-weight: 500;
        }
        #vp-status-text.recorded {
            color: #4caf50;
        }
        .path-hint {
            display: block;
            color: #78909c;
            font-size: 12px;
            margin-top: 4px;
            font-family: monospace;
        }
        #vp-record-panel {
            margin-top: 15px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            border: 1px solid rgba(79,195,247,0.2);
        }
        .vp-visualizer {
            text-align: center;
            margin-bottom: 10px;
        }
        #vp-canvas {
            border-radius: 4px;
            background: #0d2b4e;
        }
        .vp-timer {
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            color: #4fc3f7;
            margin: 10px 0;
        }
        .vp-hint {
            text-align: center;
            color: #b0bec5;
            font-size: 13px;
        }
        #btn-record-vp, #btn-stop-vp {
            padding: 8px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
            margin-right: 8px;
        }
        #btn-record-vp {
            background: #2196f3;
            color: white;
        }
        #btn-record-vp:hover {
            background: #42a5f5;
        }
        #btn-stop-vp {
            background: #f44336;
            color: white;
            display: none;
        }
        #btn-stop-vp:hover {
            background: #ef5350;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1><img src="assets/image/logo.png" alt="Logo" style="width: 25px; height: 25px; margin-right: 5px;">系统设置</h1>
        <div class="tabs">
            <div class="tab active" data-tab="ai-engine">🤖AI引擎</div>
            <div class="tab" data-tab="basic-info">ℹ️基本信息</div>
            <div class="tab" data-tab="zhipuai">🔷ZhipuAI</div>
            <div class="tab" data-tab="openai">🔧自定义OpenAI兼容</div>
            <div class="tab" data-tab="ollama">🦙Ollama和LM Studio</div>
            <div class="tab" data-tab="speech-recognition">🎙️语音识别</div>
            <div class="tab" data-tab="voiceprint">👂声纹识别</div>
            <div class="tab" data-tab="tts">🔊语音合成</div>
            <div class="tab" data-tab="image-recognition">📸图像识别</div>
            <div class="tab" data-tab="knowledge-base">📚知识库</div>
            <div class="tab" data-tab="home-assistant">🏠Home Assistant</div>
            <div class="tab" data-tab="other">⚙️其他设置</div>
            <div class="tab tab-link" onclick="window.open('http://' + window.location.hostname + ':5260/test', '_blank')">🧪浏览器测试</div>
        </div>
        <form id="config-form">
            <div class="tab-content active" id="ai-engine">
                <div class="section">
                    <h2>AI引擎选择</h2>
                    <div class="form-group">
                        <label for="prefer_asr">语音识别模式(ASR)</label>
                        <select id="prefer_asr" name="prefer_asr">
                            <option value="RealTime">RealTime(实时语音识别)</option>
                            <option value="WakeWord">WakeWord(自定义唤醒词)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="prefer_llm">对话语言模型(LLM)</label>
                        <select id="prefer_llm" name="prefer_llm">
                            <option value="ZhipuAI">ZhipuAI(云端)</option>
                            <option value="OpenAI">OpenAI(自定义)</option>
                            <option value="Ollama">Ollama(本地/局域网)</option>
                            <option value="LM Studio">LM Studio(局域网)</option>
                            <option value="AnythingLLM">AnythingLLM(局域网)</option>
                            <option value="Dify">Dify(本地/局域网)</option>
                            <option value="RKLLM">RKLLM(本地)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="prefer_tts">语音合成引擎(TTS)</label>
                        <select id="prefer_tts" name="prefer_tts">
                            <option value="edge-tts">edge-tts(云端)</option>
                            <option value="VITS">VITS(本地内置)</option>
                            <option value="GPT-SoVITS">GPT-SoVITS(局域网)</option>
                            <option value="CosyVoice">CosyVoice(局域网)</option>
                            <option value="Qwen-TTS">Qwen-TTS(局域网)</option>
                            <option value="Qwen3-TTS">Qwen3-TTS(局域网)</option>
                            <option value="VoxCPM">VoxCPM(局域网)</option>
                            <option value="Index-TTS">Index-TTS(局域网)</option>
                            <option value="CustomTTS">CustomTTS(自定义)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="prefer_vlm">图像识别引擎(VLM)</label>
                        <select id="prefer_vlm" name="prefer_vlm">
                            <option value="ZhipuAI">ZhipuAI(云端)</option>
                            <option value="OpenAI">OpenAI(自定义)</option>
                            <option value="Ollama">Ollama(本地/局域网)</option>
                            <option value="LM Studio">LM Studio(局域网)</option>
                            <option value="YOLO-OCR">YOLO-OCR(本地)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="prefer_ase">主动感知对话</label>
                        <select id="prefer_ase" name="prefer_ase">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group" style="margin-top:20px;">
                        <div class="collapse-header" onclick="toggleAdvancedParams()">
                            <span id="adv-params-icon">▶</span>
                            <span style="font-weight:bold;">⚙️ 高级参数</span>
                            <span style="color:#78909c;font-size:12px;margin-left:8px;">调整 AI 回复风格与长度</span>
                        </div>
                        <div id="advanced-params-panel" style="display:none;margin-top:12px;padding:12px;background:rgba(0,30,60,0.5);border-radius:6px;">
                            <div style="margin-bottom:16px;">
                                <label style="font-size:13px;margin-bottom:8px;">快捷预设</label>
                                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                                    <button type="button" class="preset-btn" data-preset="balanced" onclick="applyPreset('balanced')">💬 日常聊天</button>
                                    <button type="button" class="preset-btn" data-preset="analysis" onclick="applyPreset('analysis')">🔍 深度分析</button>
                                    <button type="button" class="preset-btn" data-preset="creative" onclick="applyPreset('creative')">✨ 创意发散</button>
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="temperature">Temperature（创造性）: <span id="temperature-val">0.7</span></label>
                                <input type="range" id="temperature" min="0" max="2" step="0.1" value="0.7"
                                       oninput="document.getElementById('temperature-val').textContent = this.value">
                                <div style="display:flex;justify-content:space-between;font-size:11px;color:#78909c;margin-top:2px;">
                                    <span>严谨</span><span>平衡</span><span>发散</span>
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="max_tokens">Max Tokens（最大回复长度）: <span id="max_tokens-val">4096</span></label>
                                <input type="range" id="max_tokens" min="256" max="16384" step="256" value="4096"
                                       oninput="document.getElementById('max_tokens-val').textContent = this.value">
                            </div>
                            <div class="form-group">
                                <label for="top_p">Top P（采样多样性）: <span id="top_p-val">0.9</span></label>
                                <input type="range" id="top_p" min="0" max="1" step="0.05" value="0.9"
                                       oninput="document.getElementById('top_p-val').textContent = this.value">
                            </div>
                            <button type="button" onclick="resetLlmParams()" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);color:#78909c;font-size:13px;padding:6px 12px;">恢复默认</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="tab-content" id="basic-info">
                <div class="section">
                    <h2>基本信息设置</h2>
                    <div class="form-group">
                        <label for="username">用户名</label>
                        <input type="text" id="username" name="username">
                    </div>
                    <div class="form-group">
                        <label for="mate_name">虚拟伙伴名称</label>
                        <input type="text" id="mate_name" name="mate_name">
                    </div>
                    <div class="form-group">
                        <label for="prompt">虚拟伙伴人设(对于思考模型,如需提升回答速度可在结尾添加/no_think)</label>
                        <textarea id="prompt" name="prompt" rows="10"></textarea>
                    </div>
                    <div class="form-group">
                        <label for="vrm_model_name">VRM 3D模型名称(存放于dist/assets/vrm_model文件夹)</label>
                        <input type="text" id="vrm_model_name" name="vrm_model_name">
                    </div>
                    <div class="form-group">
                        <label>Live2D模型<br>存放于dist/assets/live2d_model文件夹<br>可修改dist/assets/live2d.js进行更换<br>根据需求修改模型路径、模型坐标、模型大小参数</label>
                    </div>
                    <div class="form-group">
                        <label>MMD 3D模型和动作<br>分别存放于dist/assets/mmd_model和mmd_action文件夹<br>可分别修改dist/assets/mmd.js和mmd_vmd.js进行更换<br>根据需求修改模型路径、表情索引、动作路径参数</label>
                    </div>
                </div>
            </div>
            <div class="tab-content" id="speech-recognition">
                <div class="section">
                    <h2>语音识别设置</h2>
                    <div class="form-group">
                        <label for="speech_end_wait_time">语音识别结束等待秒数(>0.1)</label>
                        <input type="number" step="0.1" id="speech_end_wait_time" name="speech_end_wait_time">
                    </div>
                    <div class="form-group">
                        <label for="wake_word">唤醒词(推荐设置为常用的词汇)</label>
                        <input type="text" id="wake_word" name="wake_word">
                    </div>
                    <div class="form-group">
                        <label for="mic_num">麦克风编号</label>
                        <input type="number" id="mic_num" name="mic_num">
                    </div>
                    <div class="form-group">
                        <label for="sound_sense_switch">音频事件检测开关</label>
                        <select id="sound_sense_switch" name="sound_sense_switch">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="sound_sense_threshold">音频事件检测阈值(0.1~0.9)</label>
                        <input type="number" step="0.1" id="sound_sense_threshold" name="sound_sense_threshold">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="voiceprint">
                <div class="section">
                    <h2>声纹识别设置</h2>
                    <div class="form-group">
                        <label for="voiceprint_switch">声纹识别开关(开启前需将声纹文件放入指定路径)</label>
                        <select id="voiceprint_switch" name="voiceprint_switch">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="voiceprint_threshold">声纹识别阈值(0.1~0.9)</label>
                        <input type="number" step="0.1" id="voiceprint_threshold" name="voiceprint_threshold">
                    </div>
                    <div class="form-group voiceprint-record-section">
                        <label>用户声纹样本</label>
                        <div id="voiceprint-status">
                            <span id="vp-status-text">未录制</span>
                            <span id="vp-file-path" class="path-hint"></span>
                        </div>
                        <button type="button" id="btn-record-vp" onclick="startRecordVoiceprint()">🎙️ 录制声纹</button>
                        <button type="button" id="btn-stop-vp" onclick="stopRecordVoiceprint()">⏹️ 停止录制</button>
                        <div id="vp-record-panel" style="display:none;">
                            <div class="vp-visualizer">
                                <canvas id="vp-canvas" width="300" height="60"></canvas>
                            </div>
                            <div class="vp-timer" id="vp-timer">00:00</div>
                            <div class="vp-hint" id="vp-hint">请朗读：你好，我是你的主人</div>
                        </div>
                        <!-- 隐藏的表单字段，保存设置时提交路径 -->
                        <input type="hidden" id="myvoice_path" name="myvoice_path" value="">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="zhipuai">
                <div class="section">
                    <h2>ZhipuAI设置</h2>
                    <div class="form-group">
                        <label for="glm_key">ZhipuAI密钥api_key(从BigModel平台获取)</label>
                        <input type="password" id="glm_key" name="glm_key">
                    </div>
                    <div class="form-group">
                        <label for="glm_llm_model">ZhipuAI大语言模型llm-model</label>
                        <input type="text" id="glm_llm_model" name="glm_llm_model">
                    </div>
                    <div class="form-group">
                        <label for="glm_vlm_model">ZhipuAI视觉语言模型vlm-model</label>
                        <input type="text" id="glm_vlm_model" name="glm_vlm_model">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="openai">
                <div class="section">
                    <h2>OpenAI兼容设置(自定义API)</h2>
                    <div class="form-group">
                        <label for="openai_url">OpenAI兼容地址base_url</label>
                        <input type="text" id="openai_url" name="openai_url">
                    </div>
                    <div class="form-group">
                        <label for="openai_key">OpenAI兼容密钥api_key</label>
                        <input type="password" id="openai_key" name="openai_key">
                    </div>
                    <div class="form-group">
                        <label for="openai_llm_model">OpenAI兼容大语言模型llm-model</label>
                        <div style="display:flex;gap:8px;align-items:center;">
                            <select id="openai_llm_model_select" style="flex:1;" onchange="syncModelInput('llm')">
                                <option value="">-- 请选择或手动输入 --</option>
                            </select>
                            <input type="text" id="openai_llm_model" name="openai_llm_model"
                                   placeholder="自定义模型名" style="flex:1;"
                                   oninput="syncModelSelect('llm')">
                            <button type="button" onclick="fetchOpenAiModelsForSettings('llm')" title="获取模型列表">🔍</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="openai_vlm_model">OpenAI兼容视觉语言模型vlm-model</label>
                        <div style="display:flex;gap:8px;align-items:center;">
                            <select id="openai_vlm_model_select" style="flex:1;" onchange="syncModelInput('vlm')">
                                <option value="">-- 请选择或手动输入 --</option>
                            </select>
                            <input type="text" id="openai_vlm_model" name="openai_vlm_model"
                                   placeholder="自定义模型名" style="flex:1;"
                                   oninput="syncModelSelect('vlm')">
                            <button type="button" onclick="fetchOpenAiModelsForSettings('vlm')" title="获取模型列表">🔍</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="tab-content" id="ollama">
                <div class="section">
                    <h2>Ollama和LM Studio设置</h2>
                    <div class="form-group">
                        <label for="ollama_url">Ollama地址base_url</label>
                        <input type="text" id="ollama_url" name="ollama_url">
                    </div>
                    <div class="form-group">
                        <label for="ollama_llm_model">Ollama大语言模型llm-model</label>
                        <input type="text" id="ollama_llm_model" name="ollama_llm_model">
                    </div>
                    <div class="form-group">
                        <label for="ollama_vlm_model">Ollama视觉语言模型vlm-model</label>
                        <input type="text" id="ollama_vlm_model" name="ollama_vlm_model">
                    </div>
                    <div class="form-group">
                        <label for="lmstudio_url">LM Studio地址base_url</label>
                        <input type="text" id="lmstudio_url" name="lmstudio_url">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="knowledge-base">
                <div class="section">
                    <h2>知识库设置</h2>
                    <div class="form-group">
                        <label for="anything_llm_ip">AnythingLLM地址</label>
                        <input type="text" id="anything_llm_ip" name="anything_llm_ip">
                    </div>
                    <div class="form-group">
                        <label for="anything_llm_ws">AnythingLLM工作区</label>
                        <input type="text" id="anything_llm_ws" name="anything_llm_ws">
                    </div>
                    <div class="form-group">
                        <label for="anything_llm_key">AnythingLLM密钥</label>
                        <input type="text" id="anything_llm_key" name="anything_llm_key">
                    </div>
                    <div class="form-group">
                        <label for="dify_ip">Dify地址</label>
                        <input type="text" id="dify_ip" name="dify_ip">
                    </div>
                    <div class="form-group">
                        <label for="dify_key">Dify密钥</label>
                        <input type="text" id="dify_key" name="dify_key">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="tts">
                <div class="section">
                    <h2>语音合成设置</h2>
                    <div class="form-group">
                        <label for="stream_tts_switch">流式语音合成开关</label>
                        <select id="stream_tts_switch" name="stream_tts_switch">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="edge_speaker">edge-tts音色</label>
                            <select id="edge_speaker" name="edge_speaker">
                                <option value="zh-CN-XiaoyiNeural">zh-CN-XiaoyiNeural(晓艺-年轻女声)</option>
                                <option value="zh-CN-XiaoxiaoNeural">zh-CN-XiaoxiaoNeural(晓晓-成稳女声)</option>
                                <option value="zh-CN-YunjianNeural">zh-CN-YunjianNeural(云健-大型纪录片男声)</option>
                                <option value="zh-CN-YunxiNeural">zh-CN-YunxiNeural(云希-短视频热门男声)</option>
                                <option value="zh-CN-YunxiaNeural">zh-CN-YunxiaNeural(云夏-年轻男声)</option>
                                <option value="zh-CN-YunyangNeural">zh-CN-YunyangNeural(云扬-成稳男声)</option>
                                <option value="zh-CN-liaoning-XiaobeiNeural">zh-CN-liaoning-XiaobeiNeural(晓北-辽宁话女声)</option>
                                <option value="zh-CN-shaanxi-XiaoniNeural">zh-CN-shaanxi-XiaoniNeural(晓妮-陕西话女声)</option>
                                <option value="zh-HK-HiuGaaiNeural">zh-HK-HiuGaaiNeural(晓佳-粤语成稳女声)</option>
                                <option value="zh-HK-HiuMaanNeural">zh-HK-HiuMaanNeural(晓满-粤语年轻女声)</option>
                                <option value="zh-HK-WanLungNeural">zh-HK-WanLungNeural(云龙-粤语男声)</option>
                                <option value="zh-TW-HsiaoChenNeural">zh-TW-HsiaoChenNeural(晓辰-台湾话年轻女声)</option>
                                <option value="zh-TW-HsiaoYuNeural">zh-TW-HsiaoYuNeural(晓宇-台湾话成稳女声)</option>
                                <option value="zh-TW-YunJheNeural">zh-TW-YunJheNeural(云哲-台湾话男声)</option>
                                <option value="ja-JP-KeitaNeural">ja-JP-KeitaNeural(佳太-日语男声)</option>
                                <option value="ja-JP-NanamiNeural">ja-JP-NanamiNeural(七海-日语女声)</option>
                            </select>
                    </div>
                    <div class="form-group">
                        <label for="edge_rate">edge-tts语速</label>
                        <input type="text" id="edge_rate" name="edge_rate">
                    </div>
                    <div class="form-group">
                        <label for="edge_pitch">edge-tts音高</label>
                        <input type="text" id="edge_pitch" name="edge_pitch">
                    </div>
                    <div class="form-group">
                        <label for="tts_cache_clean_interval_days">音频缓存清理周期（天）</label>
                        <input type="number" id="tts_cache_clean_interval_days" name="tts_cache_clean_interval_days" min="1" max="365">
                        <small style="color:#888;font-size:12px;">定时清理非活跃会话音频的间隔，默认 7 天</small>
                    </div>
                    <div class="form-group">
                        <label for="tts_cache_session_soft_limit">单会话音频软上限（个）</label>
                        <input type="number" id="tts_cache_session_soft_limit" name="tts_cache_session_soft_limit" min="100" max="10000">
                        <small style="color:#888;font-size:12px;">单个会话最多保留的音频数量，超过时自动删除最旧的，默认 1000</small>
                    </div>
                    <div class="form-group">
                        <label for="vits_model_name">VITS-ONNX模型名称(存放于data/model/TTS文件夹)</label>
                        <input type="text" id="vits_model_name" name="vits_model_name">
                    </div>
                    <div class="form-group">
                        <label for="gsv_api">GPT-SoVITS地址</label>
                        <input type="text" id="gsv_api" name="gsv_api">
                    </div>
                    <div class="form-group">
                        <label for="gsv_prompt">GPT-SoVITS参考音频文本</label>
                        <input type="text" id="gsv_prompt" name="gsv_prompt">
                    </div>
                    <div class="form-group">
                        <label for="gsv_ref_audio_path">GPT-SoVITS参考音频路径</label>
                        <input type="text" id="gsv_ref_audio_path" name="gsv_ref_audio_path">
                    </div>
                    <div class="form-group">
                        <label for="gsv_prompt_lang">GPT-SoVITS参考音频语言</label>
                        <input type="text" id="gsv_prompt_lang" name="gsv_prompt_lang">
                    </div>
                    <div class="form-group">
                        <label for="gsv_lang">GPT-SoVITS合成输出语言</label>
                        <input type="text" id="gsv_lang" name="gsv_lang">
                    </div>
                    <div class="form-group">
                        <label for="cosy_api">CosyVoice地址</label>
                        <input type="text" id="cosy_api" name="cosy_api">
                    </div>
                    <div class="form-group">
                        <label for="qwentts_api">Qwen-TTS地址</label>
                        <input type="text" id="qwentts_api" name="qwentts_api">
                    </div>
                    <div class="form-group">
                        <label for="qwentts_model">Qwen-TTS模型</label>
                        <input type="text" id="qwentts_model" name="qwentts_model">
                    </div>
                    <div class="form-group">
                        <label for="qwentts_voice">Qwen3-TTS音色</label>
                        <select id="qwentts_voice" name="qwentts_voice">
                            <option value="ono_anna">ono_anna(日式女声)</option>
                            <option value="vivian">vivian(默认女声)</option>
                            <option value="serena">serena(女声)</option>
                            <option value="sohee">sohee(韩式女声)</option>
                            <option value="aiden">aiden(男声)</option>
                            <option value="dylan">dylan(男声)</option>
                            <option value="eric">eric(男声)</option>
                            <option value="ryan">ryan(男声)</option>
                            <option value="uncle_fu">uncle_fu(大叔男声)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="voxcpm_api">VoxCPM地址</label>
                        <input type="text" id="voxcpm_api" name="voxcpm_api">
                    </div>
                    <div class="form-group">
                        <label for="index_api">Index-TTS地址</label>
                        <input type="text" id="index_api" name="index_api">
                    </div>
                    <div class="form-group">
                        <label for="custom_tts_url">自定义TTS地址</label>
                        <input type="text" id="custom_tts_url" name="custom_tts_url">
                    </div>
                    <div class="form-group">
                        <label for="custom_tts_model">自定义TTS模型</label>
                        <input type="text" id="custom_tts_model" name="custom_tts_model">
                    </div>
                    <div class="form-group">
                        <label for="custom_tts_voice">自定义TTS音色</label>
                        <input type="text" id="custom_tts_voice" name="custom_tts_voice">
                    </div>
                    <div class="form-group">
                        <label for="custom_tts_key">自定义TTS密钥</label>
                        <input type="password" id="custom_tts_key" name="custom_tts_key">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="image-recognition">
                <div class="section">
                    <h2>图像识别设置</h2>
                    <div class="form-group">
                        <label for="cam_num">摄像头编号</label>
                        <input type="number" id="cam_num" name="cam_num">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="home-assistant">
                <div class="section">
                    <h2>Home Assistant智能家居设置</h2>
                    <div class="form-group">
                        <label for="ha_api">Home Assistant地址</label>
                        <input type="text" id="ha_api" name="ha_api">
                    </div>
                    <div class="form-group">
                        <label for="ha_key">Home Assistant长期访问令牌</label>
                        <input type="text" id="ha_key" name="ha_key">
                    </div>
                    <div class="form-group">
                        <label for="entity_id">Home Assistant实体ID(支持按钮类,button开头)</label>
                        <input type="text" id="entity_id" name="entity_id">
                    </div>
                </div>
            </div>
            <div class="tab-content" id="other">
                <div class="section">
                    <h2>其他设置</h2>
                    <div class="form-group">
                        <label for="net_num">无线网卡编号(该设置不影响正常使用)</label>
                        <input type="number" id="net_num" name="net_num">
                    </div>
                    <div class="form-group">
                        <label for="router_ip">路由器IP(该设置不影响正常使用)</label>
                        <input type="text" id="router_ip" name="router_ip">
                    </div>
                    <div class="form-group">
                        <label for="weather_city">天气城市</label>
                        <input type="text" id="weather_city" name="weather_city">
                    </div>
                    <div class="form-group">
                        <label for="rkllm_url">RKLLM地址</label>
                        <input type="text" id="rkllm_url" name="rkllm_url">
                    </div>
                    <div class="form-group">
                        <label for="auto_optimize_memory_switch">自动优化记忆开关</label>
                        <select id="auto_optimize_memory_switch" name="auto_optimize_memory_switch">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="welcome_voice_switch">欢迎语开关</label>
                        <select id="welcome_voice_switch" name="welcome_voice_switch">
                            <option value="on">on(开启)</option>
                            <option value="off">off(关闭)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="state_port">主机状态网页端口</label>
                        <input type="number" id="state_port" name="state_port">
                    </div>
                    <div class="form-group">
                        <label for="live2d_port">Live2D角色网页端口</label>
                        <input type="number" id="live2d_port" name="live2d_port">
                    </div>
                    <div class="form-group">
                        <label for="mmd_port">MMD 3D角色网页端口</label>
                        <input type="number" id="mmd_port" name="mmd_port">
                    </div>
                    <div class="form-group">
                        <label for="vrm_port">VRM 3D角色网页端口</label>
                        <input type="number" id="vrm_port" name="vrm_port">
                    </div>
                    <div class="form-group">
                        <label for="log_path">日志路径</label>
                        <input type="text" id="log_path" name="log_path" placeholder="logs">
                        <small style="color:#888;font-size:12px;">日志文件存放目录，默认 logs</small>
                    </div>
                    <div class="form-group">
                        <label for="log_name">日志文件名</label>
                        <input type="text" id="log_name" name="log_name" placeholder="run.log">
                        <small style="color:#888;font-size:12px;">日志文件名，默认 run.log</small>
                    </div>
                    <div class="form-group" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                        <div>
                            <label>日志大小</label>
                            <div id="log-size-display" style="color:#4fc3f7;font-size:14px;font-weight:bold;">计算中...</div>
                        </div>
                        <button type="button" id="clear-log-btn" style="background:rgba(200,0,0,0.7);border:none;color:#fff;padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px;">🗑️ 清空日志</button>
                        <button type="button" id="download-log-btn" style="background:rgba(0,150,0,0.7);border:none;color:#fff;padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px;">⬇️ 下载日志</button>
                    </div>
                </div>
            </div>
            <button type="button" id="save-btn">保存设置</button>
        </form>
    </div>
    <div class="notification" id="notification">保存成功，重启软件生效</div>
    <script>
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                const tabId = tab.getAttribute('data-tab');
                document.getElementById(tabId).classList.add('active');
            });
        });
        document.getElementById('save-btn').addEventListener('click', () => {
            const formData = new FormData(document.getElementById('config-form'));
            const configData = {};
            for (let [key, value] of formData.entries()) {
                if (!isNaN(value) && value !== '') {
                    configData[key] = Number(value);
                } else {
                    configData[key] = value;
                }
            }
            configData.llm_params = {
                temperature: parseFloat(document.getElementById('temperature').value),
                max_tokens: parseInt(document.getElementById('max_tokens').value),
                top_p: parseFloat(document.getElementById('top_p').value)
            };
            configData.llm_preset = document.querySelector('.preset-btn.active')?.dataset.preset || 'balanced';
            fetch('./save_config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const notification = document.getElementById('notification');
                    if (data.restart_required && data.restart_required.length > 0) {
                        notification.textContent = '保存成功！以下参数需重启服务后生效：' + data.restart_required.join(', ');
                    } else {
                        notification.textContent = '保存成功！所有参数已即时生效。';
                    }
                    notification.style.display = 'block';
                    setTimeout(() => {
                        notification.style.display = 'none';
                    }, 3000);
                } else {
                    alert('保存失败: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('保存失败: ' + error);
            });
        });
        window.addEventListener('DOMContentLoaded', () => {
            fetch('./get_config')
                .then(response => response.json())
                .then(data => {
                    Object.keys(data).forEach(key => {
                        const element = document.getElementById(key);
                        if (element) {
                            element.value = data[key];
                        }
                    });
                    if (data.llm_params) {
                        document.getElementById('temperature').value = data.llm_params.temperature ?? 0.7;
                        document.getElementById('temperature-val').textContent = data.llm_params.temperature ?? 0.7;
                        document.getElementById('max_tokens').value = data.llm_params.max_tokens ?? 4096;
                        document.getElementById('max_tokens-val').textContent = data.llm_params.max_tokens ?? 4096;
                        document.getElementById('top_p').value = data.llm_params.top_p ?? 0.9;
                        document.getElementById('top_p-val').textContent = data.llm_params.top_p ?? 0.9;
                    }
                    if (data.llm_preset && PRESETS[data.llm_preset]) {
                        applyPreset(data.llm_preset);
                    }
                    // 检查是否已有声纹文件
                    checkExistingVoiceprint();
                    // 加载日志大小
                    updateLogSize();
                })
                .catch(error => {
                    console.error('Error:', error);
                });
        });

        // ===== 日志大小显示与清空 =====
        function formatLogSize(bytes) {
            if (bytes >= 1024 * 1024 * 1024) {
                return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
            } else if (bytes >= 1024 * 1024) {
                return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
            } else if (bytes >= 1024) {
                return (bytes / 1024).toFixed(2) + ' KB';
            } else {
                return bytes + ' B';
            }
        }
        async function updateLogSize() {
            try {
                const resp = await fetch('./api/log_size');
                const data = await resp.json();
                const el = document.getElementById('log-size-display');
                if (el) el.textContent = data.size || '0 B';
            } catch (e) {
                console.error('获取日志大小失败:', e);
            }
        }
        document.getElementById('clear-log-btn')?.addEventListener('click', async function() {
            if (!confirm('确定要清空日志吗？此操作不可恢复。')) return;
            try {
                const resp = await fetch('./api/clear_log', { method: 'POST' });
                const data = await resp.json();
                if (data.success) {
                    showNotification('日志已清空');
                    updateLogSize();
                } else {
                    showNotification('清空失败: ' + (data.message || '未知错误'));
                }
            } catch (e) {
                showNotification('清空失败: ' + e.message);
            }
        });
        document.getElementById('download-log-btn')?.addEventListener('click', function() {
            window.location.href = './api/download_log';
        });
        // 每 10 秒刷新一次日志大小
        setInterval(updateLogSize, 10000);

        const PRESETS = {
            "balanced": { temperature: 0.7, max_tokens: 4096, top_p: 0.9, label: "日常聊天" },
            "analysis": { temperature: 0.3, max_tokens: 8192, top_p: 0.5, label: "深度分析" },
            "creative": { temperature: 0.95, max_tokens: 4096, top_p: 1.0, label: "创意发散" }
        };

        function toggleAdvancedParams() {
            const panel = document.getElementById('advanced-params-panel');
            const icon = document.getElementById('adv-params-icon');
            const isOpen = panel.style.display !== 'none';
            panel.style.display = isOpen ? 'none' : 'block';
            icon.textContent = isOpen ? '▶' : '▼';
        }

        function applyPreset(name) {
            const p = PRESETS[name];
            if (!p) return;
            document.getElementById('temperature').value = p.temperature;
            document.getElementById('temperature-val').textContent = p.temperature;
            document.getElementById('max_tokens').value = p.max_tokens;
            document.getElementById('max_tokens-val').textContent = p.max_tokens;
            document.getElementById('top_p').value = p.top_p;
            document.getElementById('top_p-val').textContent = p.top_p;

            document.querySelectorAll('.preset-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.preset === name);
            });
        }

        function resetLlmParams() {
            applyPreset('balanced');
        }

        // ===== 声纹录制功能 =====
        let vpRecorder = null;
        let vpStream = null;
        let vpChunks = [];
        let vpTimerInterval = null;
        let vpStartTime = null;

        function checkExistingVoiceprint() {
            fetch('./api/voiceprint_status')
                .then(r => r.json())
                .then(data => {
                    if (data.bound) {
                        document.getElementById('vp-status-text').textContent = '✅ 已录制';
                        document.getElementById('vp-status-text').style.color = '#4caf50';
                        document.getElementById('vp-file-path').textContent = data.path || '';
                    }
                })
                .catch(e => console.log('[Voiceprint] 状态检测失败', e));
        }

        async function startRecordVoiceprint() {
            try {
                vpStream = await navigator.mediaDevices.getUserMedia({audio: true});
                vpRecorder = new MediaRecorder(vpStream);
                vpChunks = [];

                vpRecorder.ondataavailable = e => {
                    if (e.data.size > 0) vpChunks.push(e.data);
                };

                vpRecorder.onstop = async () => {
                    const blob = new Blob(vpChunks, {type: 'audio/webm'});
                    await uploadVoiceprint(blob);
                    cleanupVpRecord();
                };

                document.getElementById('vp-record-panel').style.display = 'block';
                document.getElementById('btn-record-vp').style.display = 'none';
                document.getElementById('btn-stop-vp').style.display = 'inline-block';
                document.getElementById('vp-hint').textContent = '正在录制，请朗读：你好，我是你的主人';

                startVpVisualizer(vpStream);

                vpStartTime = Date.now();
                vpTimerInterval = setInterval(updateVpTimer, 1000);

                vpRecorder.start(100);

                setTimeout(() => {
                    if (vpRecorder && vpRecorder.state === 'recording') {
                        stopRecordVoiceprint();
                    }
                }, 10000);

            } catch (err) {
                alert('无法访问麦克风：' + err.message);
            }
        }

        function stopRecordVoiceprint() {
            if (vpRecorder && vpRecorder.state !== 'inactive') {
                vpRecorder.stop();
            }
            if (vpStream) {
                vpStream.getTracks().forEach(t => t.stop());
            }
        }

        function cleanupVpRecord() {
            clearInterval(vpTimerInterval);
            document.getElementById('vp-record-panel').style.display = 'none';
            document.getElementById('btn-record-vp').style.display = 'inline-block';
            document.getElementById('btn-stop-vp').style.display = 'none';
            document.getElementById('vp-timer').textContent = '00:00';
            vpStream = null;
            vpRecorder = null;
        }

        function updateVpTimer() {
            const elapsed = Math.floor((Date.now() - vpStartTime) / 1000);
            const min = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const sec = String(elapsed % 60).padStart(2, '0');
            document.getElementById('vp-timer').textContent = min + ':' + sec;
        }

        async function uploadVoiceprint(audioBlob) {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'voiceprint.webm');

            try {
                const res = await fetch('./api/record_voiceprint', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('vp-status-text').textContent = '✅ 已录制';
                    document.getElementById('vp-status-text').style.color = '#4caf50';
                    document.getElementById('vp-file-path').textContent = data.path;
                    document.getElementById('myvoice_path').value = data.path;
                } else {
                    alert('保存失败：' + data.message);
                }
            } catch (e) {
                alert('上传失败：' + e.message);
            }
        }

        function startVpVisualizer(stream) {
            const audioCtx = new AudioContext();
            const source = audioCtx.createMediaStreamSource(stream);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            source.connect(analyser);

            const canvas = document.getElementById('vp-canvas');
            const ctx = canvas.getContext('2d');
            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            function draw() {
                if (!vpRecorder || vpRecorder.state !== 'recording') return;
                requestAnimationFrame(draw);
                analyser.getByteFrequencyData(dataArray);

                ctx.fillStyle = '#0d2b4e';
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                const barWidth = canvas.width / dataArray.length;
                for (let i = 0; i < dataArray.length; i++) {
                    const barHeight = (dataArray[i] / 255) * canvas.height;
                    ctx.fillStyle = '#4fc3f7';
                    ctx.fillRect(i * barWidth, canvas.height - barHeight, barWidth - 1, barHeight);
                }
            }
            draw();
        }
        // ===== 声纹录制功能结束 =====

        // 同步 select 和 input
        function syncModelInput(type) {
            const select = document.getElementById('openai_' + type + '_model_select');
            const input = document.getElementById('openai_' + type + '_model');
            if (select.value) {
                input.value = select.value;
            }
        }

        function syncModelSelect(type) {
            const select = document.getElementById('openai_' + type + '_model_select');
            const input = document.getElementById('openai_' + type + '_model');
            let found = false;
            for (let i = 0; i < select.options.length; i++) {
                if (select.options[i].value === input.value) {
                    select.selectedIndex = i;
                    found = true;
                    break;
                }
            }
            if (!found) {
                select.selectedIndex = 0;
            }
        }

        function showNotification(message, type) {
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.style.backgroundColor = type === 'error' ? '#f44336' : '#4CAF50';
            notification.style.display = 'block';
            setTimeout(() => {
                notification.style.display = 'none';
            }, 3000);
        }

        async function fetchOpenAiModelsForSettings(type) {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳';

            try {
                const resp = await fetch('./api/openai_models');
                const data = await resp.json();

                if (data.status === 'success') {
                    const select = document.getElementById('openai_' + type + '_model_select');
                    const firstOption = select.options[0];
                    select.innerHTML = '';
                    select.appendChild(firstOption);

                    data.models.forEach(model => {
                        const opt = document.createElement('option');
                        opt.value = model;
                        opt.textContent = model;
                        select.appendChild(opt);
                    });

                    syncModelSelect(type);
                    showNotification('成功获取 ' + data.models.length + ' 个模型', 'success');
                } else {
                    showNotification('获取失败: ' + data.message, 'error');
                }
            } catch (e) {
                showNotification('请求异常: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🔍';
            }
        }
    </script>
</body>
</html>
"""


# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
@app5.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app5.route('/get_config')
def get_config_route():
    cfg = load_config()
    return jsonify(cfg)



# 需重启才能生效的参数白名单
_RESTART_REQUIRED_KEYS = [
    "state_port", "live2d_port", "mmd_port", "vrm_port",
    "vits_model_name", "mic_num",
    "voiceprint_switch", "voiceprint_threshold", "myvoice_path",
]


@app5.route('/save_config', methods=['POST'])
def save_config_route():
    try:
        new_config_data = request.json
        cfg = load_config()
        cfg.update(new_config_data)
        # 检查本次修改是否涉及需重启参数（仅当值实际发生变化时才提示）
        restart_required = [
            key for key in _RESTART_REQUIRED_KEYS
            if key in new_config_data and new_config_data.get(key) != cfg.get(key)
        ]
        if save_config(cfg):
            return jsonify({
                "success": True,
                "message": "保存成功",
                "restart_required": restart_required,
            })
        else:
            return jsonify({"success": False, "message": "保存设置失败"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app5.route('/api/log_size', methods=['GET'])
def api_log_size():
    """获取当前日志文件大小"""
    try:
        cfg = load_config()
        log_path = cfg.get('log_path', 'logs')
        log_name = cfg.get('log_name', 'run.log')
        log_file = os.path.join(log_path, log_name)
        size = os.path.getsize(log_file) if os.path.exists(log_file) else 0
        # 自动换算单位
        if size >= 1024 ** 3:
            size_str = f"{size / (1024 ** 3):.2f} GB"
        elif size >= 1024 ** 2:
            size_str = f"{size / (1024 ** 2):.2f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.2f} KB"
        else:
            size_str = f"{size} B"
        return jsonify({"success": True, "size": size_str, "bytes": size})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app5.route('/api/clear_log', methods=['POST'])
def api_clear_log():
    """清空日志文件（使用 truncate 方式，不删除文件，保证 tee 文件描述符继续有效）"""
    try:
        cfg = load_config()
        log_path = cfg.get('log_path', 'logs')
        log_name = cfg.get('log_name', 'run.log')
        log_file = os.path.join(log_path, log_name)
        if os.path.exists(log_file):
            # 使用 truncate 方式清空，保留文件 inode，确保 tee -a 的文件描述符继续有效
            with open(log_file, 'w', encoding='utf-8') as f:
                f.truncate(0)
            return jsonify({"success": True, "message": "日志已清空"})
        return jsonify({"success": True, "message": "日志文件不存在，无需清空"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app5.route('/api/download_log', methods=['GET'])
def api_download_log():
    """下载日志文件"""
    try:
        cfg = load_config()
        log_path = cfg.get('log_path', 'logs')
        log_name = cfg.get('log_name', 'run.log')
        log_file = os.path.join(log_path, log_name)
        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "日志文件不存在"}), 404
        return send_from_directory(
            os.path.abspath(log_path),
            log_name,
            as_attachment=True,
            download_name=log_name
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app5.route('/api/record_voiceprint', methods=['POST'])
def record_voiceprint():
    """
    接收前端上传的声纹音频（webm），转换为 16kHz 单声道 WAV 保存
    """
    if 'audio' not in request.files:
        return jsonify({"status": "error", "message": "No audio file"}), 400

    audio_file = request.files['audio']
    vp_dir = 'data/voiceprint'
    os.makedirs(vp_dir, exist_ok=True)

    temp_webm = os.path.join(vp_dir, 'temp_record.webm')
    output_wav = os.path.join(vp_dir, 'myvoice.wav')
    audio_file.save(temp_webm)

    try:
        result = subprocess.run([
            'ffmpeg', '-y', '-i', temp_webm,
            '-ar', '16000', '-ac', '1', '-acodec', 'pcm_s16le',
            output_wav
        ], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return jsonify({
                "status": "error",
                "message": "音频转换失败",
                "detail": result.stderr
            }), 500

        os.remove(temp_webm)

        return jsonify({
            "status": "success",
            "path": output_wav,
            "message": "声纹录制成功"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app5.route('/api/voiceprint_status', methods=['GET'])
def settings_voiceprint_status():
    """
    返回声纹识别状态（供设置页使用）
    """
    bound = bool(myvoice_path and os.path.exists(myvoice_path))
    return jsonify({
        "enabled": (voiceprint_switch == "on"),
        "bound": bound,
        "path": myvoice_path if bound else None
    })


@app5.route("/api/openai_models", methods=["GET"])
def api_openai_models():
    """获取 OpenAI 兼容服务的模型列表

    Query Params:
        base_url: OpenAI 兼容地址（可选，默认使用配置中的 openai_url）
        api_key: API 密钥（可选，默认使用配置中的 openai_key）

    Response:
        {"status": "success", "models": ["gpt-4o", "qwen-vl-max", ...]}
        {"status": "error", "message": "..."}
    """
    try:
        # 重新读取最新配置（用户在设置页修改后，全局变量不会自动更新）
        cfg = load_config()
        base_url = request.args.get("base_url", cfg.get("openai_url", openai_url))
        api_key = request.args.get("api_key", cfg.get("openai_key", openai_key))

        if not base_url:
            return jsonify({"status": "error", "message": "未配置 OpenAI 地址"})

        client = OpenAICompatibleClient(base_url=base_url, api_key=api_key)
        model_ids = client.models_list(timeout=30)
        return jsonify({"status": "success", "models": model_ids})

    except Exception as e:
        logging.getLogger("web_settings").error("获取模型列表失败", exc_info=True)
        return jsonify({"status": "error", "message": f"无法获取模型列表: {str(e)}"})


@app5.route('/assets/<path:path>')
def serve_static(path):  # 静态资源
    return send_from_directory('./dist/assets', path)


def _is_valid_ip(ip: str) -> bool:
    """校验 IPv4 地址格式"""
    if not ip or not isinstance(ip, str):
        return False
    pattern = re.compile(
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )
    return bool(pattern.match(ip.strip()))


def get_local_ip() -> str:
    """获取本机IP，支持 HOST_IP 环境变量覆盖"""
    # 1. 优先读取 HOST_IP 环境变量
    host_ip = os.environ.get("HOST_IP", "").strip()
    if host_ip:
        if _is_valid_ip(host_ip):
            return host_ip
        print(f"[WARN] HOST_IP 格式非法 '{host_ip}'，fallback 到自动获取")

    # 2. 自动获取
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("119.29.29.29", 1))
        ip = s.getsockname()[0]
        s.close()  # 显式关闭
    except (socket.error, OSError):
        ip = "127.0.0.1"
    return ip


config = load_config()
prefer_asr = config["prefer_asr"]
prefer_llm = config["prefer_llm"]
prefer_tts = config["prefer_tts"]
prefer_vlm = config["prefer_vlm"]
prefer_ase = config["prefer_ase"]
username = config["username"]
mate_name = config["mate_name"]
prompt = config["prompt"]
vrm_model_name = config["vrm_model_name"]
speech_end_wait_time = config["speech_end_wait_time"]
wake_word = config["wake_word"]
mic_num = config["mic_num"]
sound_sense_switch = config["sound_sense_switch"]
sound_sense_threshold = config["sound_sense_threshold"]
voiceprint_switch = config["voiceprint_switch"]
voiceprint_threshold = config["voiceprint_threshold"]
myvoice_path = config["myvoice_path"]
glm_key = config["glm_key"]
glm_llm_model = config["glm_llm_model"]
glm_vlm_model = config["glm_vlm_model"]
openai_url = config["openai_url"]
openai_key = config["openai_key"]
openai_llm_model = config["openai_llm_model"]
openai_vlm_model = config["openai_vlm_model"]
ollama_url = config["ollama_url"]
ollama_llm_model = config["ollama_llm_model"]
ollama_vlm_model = config["ollama_vlm_model"]
lmstudio_url = config["lmstudio_url"]
anything_llm_ip = config["anything_llm_ip"]
anything_llm_ws = config["anything_llm_ws"]
anything_llm_key = config["anything_llm_key"]
dify_ip = config["dify_ip"]
dify_key = config["dify_key"]
stream_tts_switch = config["stream_tts_switch"]
edge_speaker = config["edge_speaker"]
edge_rate = config["edge_rate"]
edge_pitch = config["edge_pitch"]
vits_model_name = config["vits_model_name"]
gsv_api = config["gsv_api"]
gsv_prompt = config["gsv_prompt"]
gsv_ref_audio_path = config["gsv_ref_audio_path"]
gsv_prompt_lang = config["gsv_prompt_lang"]
gsv_lang = config["gsv_lang"]
cosy_api = config["cosy_api"]
qwentts_api = config["qwentts_api"]
qwentts_model = config["qwentts_model"]
qwentts_voice = config["qwentts_voice"]
voxcpm_api = config["voxcpm_api"]
index_api = config["index_api"]
custom_tts_url = config["custom_tts_url"]
custom_tts_model = config["custom_tts_model"]
custom_tts_voice = config["custom_tts_voice"]
custom_tts_key = config["custom_tts_key"]
cam_num = config["cam_num"]
ha_api = config["ha_api"]
ha_key = config["ha_key"]
entity_id = config["entity_id"]
net_num = config["net_num"]
router_ip = config["router_ip"]
weather_city = config["weather_city"]
rkllm_url = config["rkllm_url"]
auto_optimize_memory_switch = config["auto_optimize_memory_switch"]
welcome_voice_switch = config["welcome_voice_switch"]
state_port = config["state_port"]
live2d_port = config["live2d_port"]
mmd_port = config["mmd_port"]
vrm_port = config["vrm_port"]
tts_cache_clean_interval_days = config["tts_cache_clean_interval_days"]
tts_cache_session_soft_limit = config["tts_cache_session_soft_limit"]
log_path = config["log_path"]
log_name = config["log_name"]
lan_ip = get_local_ip()


def run_settings_web():  # 启动系统设置服务
    print(f"系统设置网址：http://{lan_ip}:5250\n")
    app5.run(port=5250, host="0.0.0.0")
