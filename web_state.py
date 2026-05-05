from flask import Flask, render_template_string, request, jsonify, send_from_directory, Response, stream_with_context
import logging
import os
import subprocess
import psutil
import time
import base64
from llm import (
    chat_preprocess, chat_with_history,
)
from web_settings import (
    get_config_value, get_config,
    lan_ip, live2d_port, mmd_port, vrm_port, state_port,
    voiceprint_switch, myvoice_path,
    prefer_llm, prefer_vlm, mate_name, username,
    glm_key, glm_llm_model, openai_url, openai_key, openai_llm_model,
    ollama_url, ollama_llm_model, lmstudio_url,
    dify_key, anything_llm_ip, anything_llm_ws, anything_llm_key,
    rkllm_url, save_config, load_config
)
from function import get_wan_info, get_lan_info, get_wifi_info
from conversation import (
    create_session, get_session, list_sessions, save_message, get_session_messages,
    update_session_message_count, generate_title_async, update_session_with_lock,
    search_messages
)
from file_parser import parse_file, check_dependencies
from archive import archive_old_sessions
import json

app = Flask(__name__, static_folder='dist')
logging.getLogger('werkzeug').setLevel(logging.ERROR)
state_web_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="assets/image/logo.png"/>
    <title>主机状态 - Aivmate LX3</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <link rel="stylesheet" href="/assets/css/state-web.css?v=4">
</head>
<body>
    <div id="app-container">
        <!-- 顶部状态栏 (40px, hover展开显示详细信息) -->
        <div id="status-bar">
            <div class="status-bar-collapsed">
                <span class="status-logo"><img src="assets/image/logo.png" alt="Logo"> Aivmate LX3</span>
                <span class="status-metrics">
                    <span id="cpu_badge">CPU: <span id="cpu_percent">-</span></span>
                    <span id="mem_badge">MEM: <span id="memory_percent">-</span></span>
                    <span id="temp_badge">TEMP: <span id="temp">-</span></span>
                    <span id="wan_badge">WAN: <span id="wan_info">-</span></span>
                    <span id="lan_badge">LAN: <span id="lan_info">-</span></span>
                    <span id="wifi_badge">WIFI: <span id="wifi_info">-</span></span>
                </span>
                <span class="status-menu">
                    <button id="dropdown-btn">📜</button>
                    <div id="dropdown-content" class="dropdown-content">
                        <button id="live2d-btn">👤Live2D角色</button>
                        <button id="mmd-btn">👤MMD 3D角色</button>
                        <button id="vmd-btn">💃MMD 3D动作</button>
                        <button id="vrm-btn">👤VRM 3D角色</button>
                        <button id="settings-btn">⚙️系统设置</button>
                    </div>
                </span>
            </div>
            <div class="status-bar-expanded">
                <div class="expanded-metrics-row">
                    <div class="metric-box">
                        <div class="metric-label">💻CPU使用率</div>
                        <div class="metric-value" id="cpu_percent_exp">0%</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">💾内存使用率</div>
                        <div class="metric-value" id="memory_percent_exp">0%</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">🌡️内部温度</div>
                        <div class="metric-value" id="temp_exp">0℃</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">🌍外部网络</div>
                        <div class="metric-value" id="wan_info_exp">-</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">🏠内部网络</div>
                        <div class="metric-value" id="lan_info_exp">-</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">📶WiFi</div>
                        <div class="metric-value" id="wifi_info_exp">-</div>
                    </div>
                </div>
            </div>
        </div>
        <!-- 主内容区: 侧边栏 + 聊天区 + 角色面板 -->
        <div id="main-content">
            <div id="session-sidebar">
                <!-- 全局搜索（P2 Day 5 新增） -->
                <div id="global-search-box">
                    <input type="text" id="global-search-input"
                           placeholder="🔍 搜索所有会话..."
                           autocomplete="off">
                    <div id="global-search-results" class="hidden">
                        <div class="search-results-header">
                            <span id="global-search-count">0 条结果</span>
                            <button id="global-search-close" title="关闭">✕</button>
                        </div>
                        <div id="global-search-list"></div>
                    </div>
                </div>
                <div class="sidebar-header">
                    <button id="new-session-btn" title="新对话">+ 新对话</button>
                    <button id="sidebar-toggle" title="收起/展开">☰</button>
                </div>
                <div class="session-list" id="session-list"></div>
            </div>
            <div id="chat-area">
                <div id="chat-main-wrapper">
                    <div class="chat-container">
                        <div class="voice-bar">
                            <button id="sidebar-expand-btn" class="sidebar-expand-btn" title="展开侧边栏">☰</button>
                            <span id="tts-status" class="tts-status"></span>
                            <label class="voice-toggle" title="自动朗读">
                                <input type="checkbox" id="autoVoice">
                                <span class="switch"></span>
                                <span>🔊</span>
                            </label>
                            <button id="search-btn" class="search-btn" title="搜索 (Ctrl+F)">🔍</button>
                        </div>
                        <div id="voice-hint">💡 首次使用请点击页面任意位置，以启用语音自动播放</div>
                        <!-- 搜索浮层（P2 Day 4 新增） -->
                        <div id="search-float" style="display:none;">
                            <div class="search-box">
                                <span class="search-icon">🔍</span>
                                <input type="text" id="search-input" placeholder="搜索当前会话..." autocomplete="off">
                                <span class="search-count" id="search-count">0/0</span>
                                <button id="search-prev" title="上一项">▲</button>
                                <button id="search-next" title="下一项">▼</button>
                                <button id="search-close" title="关闭 (Esc)">✕</button>
                            </div>
                        </div>
                        <div class="chat-messages" id="chat_messages">
                            <div class="message ai-message">
                                <div>哈喽,{{ username }},我是{{ mate_name }},欢迎使用Aivmate LX3✨</div>
                                <div class="timestamp">刚刚</div>
                            </div>
                        </div>
                        <div id="session-loading" class="session-loading-msg" style="display:none;" title="小月正在思考与回答...">
                            <div class="spinner"></div>
                        </div>

                        <div id="upload-preview" style="display:none;"></div>
                        <div id="file-preview" style="display:none; margin-bottom:8px; padding:8px 12px; background:rgba(0,100,200,0.15); border:1px solid rgba(0,150,255,0.3); border-radius:6px; font-size:13px; color:#a0d0ff;">
                            <div style="display:flex; align-items:center; justify-content:space-between;">
                                <span id="file-preview-name">📄 filename.txt</span>
                                <button onclick="clearFilePreview()" style="background:none; border:none; color:#ff6b6b; cursor:pointer; font-size:16px;">✕</button>
                            </div>
                            <div id="file-preview-content" style="margin-top:4px; color:#88bbdd; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"></div>
                        </div>
                        <div id="camera-panel">
                            <video id="cam-video" autoplay playsinline width="320" height="240"></video>
                            <canvas id="cam-canvas" style="display:none;"></canvas>
                            <div class="cam-actions">
                                <button onclick="capturePhoto()" style="background:#0066cc;color:white;">📸 拍照</button>
                                <button onclick="closeCamera()" style="background:#660000;color:white;">❌ 关闭</button>
                            </div>
                        </div>
                        <div class="chat-input-container">
                            <button id="clear_button" class="clear-button">➕新对话</button>
                            <select id="preset-select" class="preset-select" title="切换对话风格">
                                <option value="balanced">💬 日常</option>
                                <option value="analysis">🔍 深度</option>
                                <option value="creative">✨ 创意</option>
                            </select>
                            <button id="btn-switch-model" class="clear-button" onclick="showModelSwitcher()" title="切换模型">⚙️ 模型</button>
                            <div class="upload-menu-wrapper">
                                <button class="upload-btn" onclick="toggleUploadMenu(event)" title="附件">📎</button>
                                <div id="upload-menu" class="upload-menu" style="display:none;">
                                    <div class="upload-menu-item" onclick="document.getElementById('image-upload-input').click();toggleUploadMenu(event);">🖼️ 上传图片</div>
                                    <div class="upload-menu-item" onclick="document.getElementById('file-upload-input').click();toggleUploadMenu(event);">📎 上传文件</div>
                                    <div class="upload-menu-item" onclick="toggleCamera();toggleUploadMenu(event);">🎥 拍照</div>
                                </div>
                            </div>
                            <button id="mic-btn" class="clear-button" onclick="toggleMic()" title="语音输入">🎤</button>
                            <input type="file" id="image-upload-input" accept="image/*" style="display:none;" onchange="handleImageUpload(this)">
                            <input type="file" id="file-upload-input" accept=".txt,.md,.pdf,.docx" style="display:none;" onchange="handleFileUpload(this)">
                            <input type="text" id="chat_input" placeholder="请输入消息..." class="chat-input">
                            <button id="send_button" class="send-button">发送</button>
                        </div>
                    </div>
                    <!-- P2 新增：导航栏 -->
                    <div id="chat-nav-panel">
                        <div class="chat-nav-header">
                            <span>📋 对话节点</span>
                            <button id="chat-nav-toggle" title="折叠">▶</button>
                        </div>
                        <div class="chat-nav-content" id="chat-nav-content"></div>
                    </div>
                </div>
            </div>
            <!-- 角色面板: 手机边框样式 -->
            <div id="char-collapse-wrapper">
                <button id="char-collapse-btn" class="char-collapse-btn" title="展开/折叠角色面板">▶</button>
            </div>
            <div id="char-panel" class="phone-frame">
                <button id="char-close-btn" class="char-close-btn" title="折叠">✕</button>
                <div class="phone-notch">
                    <span class="phone-time" id="phone-time">12:00</span>
                    <span class="phone-icons">📶 🔋</span>
                </div>
                <div class="phone-screen">
                    <iframe id="char-iframe" src="" loading="lazy" allow="autoplay"></iframe>
                    <div class="char-loading" id="char-loading">
                        <div class="char-loading-spinner"></div>
                        <span>加载角色中...</span>
                    </div>
                </div>
                <div class="phone-controls">
                    <button class="char-tab active" data-type="live2d">👤 Live2D</button>
                    <button class="char-tab" data-type="mmd">👤 MMD</button>
                    <button class="char-tab" data-type="vrm">👤 VRM</button>
                </div>
                <div class="phone-home-bar"></div>
            </div>
        </div>
    </div>
    <!-- 自定义模态框 -->
    <div id="custom-modal" class="modal-overlay" style="display:none;">
        <div class="modal-box">
            <div class="modal-title" id="modal-title">提示</div>
            <div class="modal-body" id="modal-body"></div>
            <input type="text" id="modal-input" class="modal-input" style="display:none;">
            <div class="modal-actions">
                <button id="modal-cancel" class="modal-btn modal-btn-cancel">取消</button>
                <button id="modal-confirm" class="modal-btn modal-btn-confirm">确认</button>
            </div>
        </div>
    </div>
    <script src="/assets/js/state-web.js?v=4"></script>
</body>
</html>"""



# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
@app.route('/')
def index():
    current_mate_name = get_config_value("mate_name", mate_name)
    current_username = get_config_value("username", username)
    return render_template_string(state_web_html, mate_name=current_mate_name, username=current_username)


@app.route('/api/info')
def get_info():
    try:
        temps = psutil.sensors_temperatures()
        temp = int(temps[next(iter(temps))][0].current)
    except Exception:
        temp = "-"
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory_percent = psutil.virtual_memory().percent
    wan_info = get_wan_info()
    lan_info = get_lan_info()
    wifi_info = get_wifi_info()
    # 检测是否经过 nginx 反代（X-Forwarded-For 头由 nginx 添加）
    is_proxied = request.headers.get('X-Forwarded-For') is not None
    if is_proxied:
        # 通过 nginx 反代时使用相对路径，设置页用 Host 头中的宿主机地址
        host = request.headers.get('Host', lan_ip)
        host_ip = host.split(':')[0]  # 去掉端口部分
        live2d_url = '/live2d/'
        mmd_url = '/mmd/'
        vmd_url = '/mmd/vmd'
        vrm_url = '/vrm/'
        settings_url = f"http://{host_ip}:5250"
    else:
        # 直接访问时使用绝对 URL
        live2d_url = f"http://{lan_ip}:{live2d_port}"
        mmd_url = f"http://{lan_ip}:{mmd_port}"
        vmd_url = f"http://{lan_ip}:{mmd_port}/vmd"
        vrm_url = f"http://{lan_ip}:{vrm_port}"
        settings_url = f"http://{lan_ip}:5250"
    return jsonify({
        'cpu_percent': cpu_percent, 'memory_percent': memory_percent, 'temp': temp, 'wan_info': wan_info,
        'lan_info': lan_info, 'wifi_info': wifi_info,
        'live2d_url': live2d_url, 'mmd_url': mmd_url, 'vmd_url': vmd_url,
        'vrm_url': vrm_url, 'settings_url': settings_url,
        'asr_mode': os.environ.get('ASR_MODE', 'vad')})


def _save_base64_image(session_id: str, image_base64: str) -> str | None:
    """将 base64 图片保存到文件系统，返回相对路径

    Args:
        session_id: 会话 UUID
        image_base64: base64 编码的图片数据（可能包含 data:image/... 前缀）

    Returns:
        str | None: 图片相对路径，保存失败返回 None
    """
    try:
        # 处理 data:image/jpeg;base64, 前缀
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        img_data = base64.b64decode(image_base64)
        img_dir = os.path.join("data", "sessions", session_id, "images")
        os.makedirs(img_dir, exist_ok=True)
        img_name = f"img_{int(time.time() * 1000)}.jpg"
        img_path = os.path.join(img_dir, img_name)
        with open(img_path, "wb") as f:
            f.write(img_data)
        return os.path.join("sessions", session_id, "images", img_name)
    except Exception as e:
        logging.getLogger("web_state").error(f"保存图片失败: {e}", exc_info=True)
        return None


def _save_file_content(session_id: str, file_content: str, file_name: str) -> str | None:
    """将文件内容保存到文件系统，返回相对路径

    注意：保存时将扩展名统一改为 .txt，避免 .pdf/.docx 文件实际内容为纯文本。

    Args:
        session_id: 会话 UUID
        file_content: 文件文本内容
        file_name: 原始文件名（仅用于生成 .txt 文件名）

    Returns:
        str | None: 文件相对路径，保存失败返回 None
    """
    try:
        file_dir = os.path.join("data", "sessions", session_id, "files")
        os.makedirs(file_dir, exist_ok=True)
        # 扩展名统一改为 .txt，避免 .pdf/.docx 文件实际存储纯文本造成歧义
        base_name = os.path.splitext(file_name)[0]
        txt_name = base_name + ".txt"
        file_path = os.path.join(file_dir, txt_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_content)
        return os.path.join("sessions", session_id, "files", txt_name)
    except Exception as e:
        logging.getLogger("web_state").error(f"保存文件失败: {e}", exc_info=True)
        return None


def _build_llm_config() -> dict:
    """构建 LLM 配置字典，供标题生成使用（实时读取）

    Returns:
        dict: LLM 配置
    """
    cfg = get_config()
    return {
        "prefer_llm": cfg.get("prefer_llm", prefer_llm),
        "glm_key": cfg.get("glm_key", glm_key),
        "glm_llm_model": cfg.get("glm_llm_model", glm_llm_model),
        "openai_url": cfg.get("openai_url", openai_url),
        "openai_key": cfg.get("openai_key", openai_key),
        "openai_llm_model": cfg.get("openai_llm_model", openai_llm_model),
        "ollama_url": cfg.get("ollama_url", ollama_url),
        "ollama_llm_model": cfg.get("ollama_llm_model", ollama_llm_model),
        "lmstudio_url": cfg.get("lmstudio_url", lmstudio_url),
    }


@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """改造后的聊天接口，支持 session_id 与会话隔离

    Request:
        {
            "session_id": "...",       // 可选，空则自动新建
            "message": "...",
            "image_base64": "...",     // 可选
            "prev_image_base64": "...", // 可选（P0 兼容）
            "file_content": "...",     // 可选
            "file_name": "..."         // 可选
        }

    Response:
        {
            "status": "success",
            "response": "AI 回复",
            "session_id": "...",
            "title": "...",
            "history": [
                {"role": "user", "content": "...", "image_path": "...", "timestamp": ...},
                {"role": "assistant", "content": "...", "timestamp": ...}
            ]
        }
    """
    data = request.json
    message = data.get('message', '')
    image_base64 = data.get('image_base64', None)
    prev_image_base64 = data.get('prev_image_base64', None)
    file_content = data.get('file_content', None)
    file_name = data.get('file_name', None)
    session_id = data.get('session_id', None)

    try:
        # 1. 检查/创建会话
        if not session_id:
            session_id = create_session()
        else:
            session = get_session(session_id)
            if not session:
                # 会话不存在，自动新建（不报错）
                session_id = create_session()

        # 2. 加载该会话历史消息
        session_messages = get_session_messages(session_id, limit=20)

        # 3. 保存图片到文件系统（如有）
        image_path = None
        if image_base64:
            image_path = _save_base64_image(session_id, image_base64)

        # 4. 保存文件到文件系统（如有）
        file_path = None
        if file_content and file_name:
            file_path = _save_file_content(session_id, file_content, file_name)

        # 5. 构造发送给 LLM 的消息（含文件前缀）
        final_message = message
        if file_content and file_name:
            final_message = f"[文件: {file_name}]\n{file_content}\n\n用户说: {message}"

        # 6. 保存用户消息到 SQLite（原始 message，不含文件前缀）
        save_message(
            session_id, "user", content=message,
            image_path=image_path, file_name=file_name, file_path=file_path,
            file_content=file_content
        )

        # 7. 构建用于 LLM 的历史消息数组（OpenAI 格式）
        history_for_llm = []
        for m in session_messages:
            history_for_llm.append({
                "role": m["role"],
                "content": m["content"],
            })

        # 8. 调用路径 2：chat_with_history（不读写全局 openai_history）
        # 注意：VLM 图片分析仍走 chat_preprocess（P0 兼容）
        if image_base64 and get_config_value("prefer_vlm", prefer_vlm) != "off":
            # 有图片时，走 VLM 分析（复用 P0 逻辑）
            res = chat_preprocess(
                final_message, image_base64=image_base64,
                prev_image_base64=prev_image_base64,
                file_content=file_content, file_name=file_name
            )
        else:
            # 无图片时，走新的 chat_with_history
            res = chat_with_history(final_message, history_for_llm)

        if res is None:
            res = "操作已执行"

        # 8. 保存 AI 回复到 SQLite
        save_message(session_id, "assistant", content=res)

        # 9. 更新会话消息计数
        new_count = len(session_messages) + 2  # user + assistant
        update_session_message_count(session_id, new_count)

        # 10. 首次对话异步触发标题生成（message_count 从 0 -> 1 时）
        if new_count == 2:
            generate_title_async(
                session_id, message, res, _build_llm_config()
            )

        # 11. 获取最新消息列表返回给前端
        latest_messages = get_session_messages(session_id, limit=20)
        session = get_session(session_id)

        return jsonify({
            'status': 'success',
            'response': res,
            'session_id': session_id,
            'title': session['title'] if session else '',
            'history': latest_messages,
        })

    except Exception as e:
        logging.getLogger("web_state").error("handle_chat 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/audio_status', methods=['POST'])
def audio_status():
    from tts import set_tts_playing, _playing_files
    try:
        data = request.get_json() or {}
        playing = data.get('playing', False)
        set_tts_playing(playing)

        # 新增：更新播放中文件集合
        current_file = data.get("current_file")
        if current_file:
            if playing:
                _playing_files.add(current_file)
            else:
                _playing_files.discard(current_file)

        return jsonify({'status': 'success'})
    except Exception as e:
        logging.getLogger("web_state").error(f"/api/audio_status 异常: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/tts_segment', methods=['POST'])
def tts_segment():
    """
    流式 TTS：立即生成第 1 段并返回，剩余段后台异步生成。
    支持 Session 隔离：音频存储到 cache_voice/{session_id}/ 子目录。
    接收 JSON: {"text": "要合成的文本", "engine": "edge-tts", "session_id": "..."}
    返回 JSON: {
        "status": "success",
        "audio_urls": ["/assets/cache_voice/{sid}/xxx.mp3", ...],
        "first_url": "/assets/cache_voice/{sid}/xxx.mp3",
        "batch_id": "tts_xxx",
        "total": 12,
        "cached": true/false
    }
    """
    from tts import generate_tts_streaming
    data = request.json or {}
    text = data.get('text', '')
    engine = data.get('engine', None)
    session_id = data.get('session_id', '')
    if not text:
        return jsonify({'status': 'error', 'message': '文本未提供'})
    try:
        result = generate_tts_streaming(text, engine=engine, session_id=session_id)
        return jsonify({
            'status': 'success',
            'audio_urls': result['audio_urls'],
            'first_url': result['first_url'],
            'batch_id': result['batch_id'],
            'total': result['total'],
            'cached': result.get('cached', False),
        })
    except Exception as e:
        logging.getLogger("web_state").error("tts_segment 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/tts_progress', methods=['POST'])
def tts_progress():
    """
    查询流式 TTS 批次进度。
    接收 JSON: {"batch_id": "tts_xxx"}
    返回 JSON: {"status": "success", "urls": [...], "done": true/false, "total": 12}
    """
    from tts import get_tts_batch_progress
    data = request.json or {}
    batch_id = data.get('batch_id', '')
    if not batch_id:
        return jsonify({'status': 'error', 'message': 'batch_id 未提供'})
    try:
        return jsonify(get_tts_batch_progress(batch_id))
    except Exception as e:
        logging.getLogger("web_state").error("tts_progress 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/voiceprint_status', methods=['GET'])
def voiceprint_status():
    """
    返回声纹识别状态：
    {"enabled": true/false, "bound": true/false, "settings_url": "http://..."}
    """
    enabled = (voiceprint_switch == "on")
    bound = bool(myvoice_path and os.path.exists(myvoice_path))
    # 检测是否经过 nginx 反代
    is_proxied = request.headers.get('X-Forwarded-For') is not None
    if is_proxied:
        host = request.headers.get('Host', lan_ip)
        host_ip = host.split(':')[0]
        settings_url = f"http://{host_ip}:5250"
    else:
        settings_url = f"http://{lan_ip}:5250"
    return jsonify({
        "enabled": enabled,
        "bound": bound,
        "settings_url": settings_url
    })


@app.route('/api/asr', methods=['POST'])
def api_asr():
    """
    接收前端上传的音频文件（webm/ogg/wav 等格式）
    转换为 WAV 后调用 asr.py 的 recognize_audio() 进行识别
    返回 JSON: {"text": "识别结果", "status": "success"}
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file"})

    audio_file = request.files['audio']
    cache_dir = 'data/cache'
    os.makedirs(cache_dir, exist_ok=True)
    temp_path = os.path.join(cache_dir, 'browser_record.webm')
    wav_path = os.path.join(cache_dir, 'browser_record.wav')
    audio_file.save(temp_path)

    # 使用 ffmpeg 转换为 16kHz 单声道 WAV
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', temp_path, '-ar', '16000', '-ac', '1', wav_path],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "音频转换失败", "detail": str(e)})

    # 调用 ASR 识别
    # 修复：用 wave 正确提取 PCM 数据，避免 recognize_audio_from_file 把完整 WAV 字节（含 RIFF 头）
    # 当作原始 PCM 传给 recognize_audio，导致双层 WAV 包装 + 时长计算异常
    import wave
    from asr import recognize_audio
    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            framerate = wf.getframerate()
            if n_channels != 1 or framerate != 16000:
                return jsonify({"error": f"音频格式不支持: {n_channels}ch/{framerate}Hz"})
            pcm_data = wf.readframes(wf.getnframes())
        text = recognize_audio(pcm_data, skip_duration_check=True)
        return jsonify({"text": text, "status": "success"})
    except Exception as e:
        return jsonify({"error": "识别失败", "detail": str(e)})


test_page_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VCP-Mate 浏览器能力测试</title>
    <style>
        * { box-sizing: border-box; }
        body {
            background-color: #1a1a1a;
            color: #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #ffffff;
            margin-bottom: 30px;
            font-size: 24px;
        }
        .card {
            background-color: #2a2a2a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .card-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 16px;
            color: #ffffff;
            border-bottom: 1px solid #444;
            padding-bottom: 10px;
        }
        button {
            background-color: #0066cc;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-right: 10px;
            margin-bottom: 10px;
            transition: background-color 0.2s;
        }
        button:hover {
            background-color: #0052a3;
        }
        button:disabled {
            background-color: #555;
            cursor: not-allowed;
        }
        .status {
            margin-top: 10px;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 14px;
            display: inline-block;
        }
        .status-waiting { background-color: #4a4a2a; color: #ffcc00; }
        .status-playing { background-color: #2a4a2a; color: #66ff66; }
        .status-done { background-color: #2a3a4a; color: #66ccff; }
        .status-error { background-color: #4a2a2a; color: #ff6666; }
        input[type="range"] {
            width: 200px;
            margin-left: 10px;
        }
        .volume-label {
            margin-left: 10px;
            font-size: 14px;
            color: #aaa;
        }
        .viz-container {
            display: flex;
            align-items: flex-end;
            height: 60px;
            gap: 3px;
            margin-top: 10px;
        }
        .viz-bar {
            flex: 1;
            background-color: #00cc66;
            border-radius: 2px 2px 0 0;
            min-height: 2px;
            transition: height 0.05s;
        }
        video {
            border-radius: 8px;
            margin-top: 10px;
            background-color: #000;
        }
        .snapshot-preview {
            margin-top: 10px;
            max-width: 320px;
            border-radius: 8px;
            border: 2px solid #444;
        }
        .permission-hint {
            color: #ffaa66;
            font-size: 14px;
            margin-top: 10px;
        }
        .audio-player {
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧪 VCP-Mate 浏览器能力测试</h1>

        <div class="card">
            <div class="card-title">🔊 音频输出测试</div>
            <button id="btn-play-tone">🔊 播放测试音</button>
            <input type="range" id="volume-slider" min="0" max="100" value="50">
            <span class="volume-label" id="volume-label">50%</span>
            <div id="audio-status" class="status status-waiting">等待</div>
        </div>

        <div class="card">
            <div class="card-title">🎤 麦克风录制回放测试</div>
            <button id="btn-mic-test">🎤 开始麦克风测试</button>
            <button id="btn-playback" disabled>▶️ 回放录音</button>
            <div class="viz-container" id="mic-viz"></div>
            <div id="mic-status" class="status status-waiting">等待</div>
            <audio id="playback-audio" class="audio-player" controls style="display:none; margin-top:10px;"></audio>
            <div id="mic-error" class="permission-hint" style="display:none;"></div>
        </div>

        <div class="card">
            <div class="card-title">📷 摄像头采集测试</div>
            <button id="btn-cam-open">📷 打开摄像头</button>
            <button id="btn-snapshot" disabled>📸 截取画面</button>
            <button id="btn-cam-close" disabled>⏹️ 关闭摄像头</button>
            <br>
            <video id="cam-video" width="640" height="480" autoplay playsinline style="display:none;"></video>
            <div id="cam-status" class="status status-waiting">等待</div>
            <div id="snapshot-container"></div>
            <div id="cam-error" class="permission-hint" style="display:none;"></div>
        </div>
    </div>

    <script>
    (function() {
        // ===== 音频输出测试 =====
        const btnPlay = document.getElementById('btn-play-tone');
        const volSlider = document.getElementById('volume-slider');
        const volLabel = document.getElementById('volume-label');
        const audioStatus = document.getElementById('audio-status');
        let audioCtx = null;

        volSlider.addEventListener('input', () => {
            volLabel.textContent = volSlider.value + '%';
        });

        btnPlay.addEventListener('click', () => {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const volume = parseInt(volSlider.value) / 100;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'sine';
            osc.frequency.value = 1000;
            gain.gain.value = volume;
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            audioStatus.textContent = '播放中';
            audioStatus.className = 'status status-playing';
            setTimeout(() => {
                osc.stop();
                audioStatus.textContent = '完成';
                audioStatus.className = 'status status-done';
            }, 1000);
        });

        // ===== 麦克风测试 =====
        const btnMic = document.getElementById('btn-mic-test');
        const btnPlayback = document.getElementById('btn-playback');
        const micStatus = document.getElementById('mic-status');
        const micViz = document.getElementById('mic-viz');
        const playbackAudio = document.getElementById('playback-audio');
        const micError = document.getElementById('mic-error');
        let micStream = null;
        let mediaRecorder = null;
        let recordedChunks = [];
        let micAudioCtx = null;
        let micAnalyser = null;
        let micSource = null;
        let micRaf = null;

        // 创建可视化条
        for (let i = 0; i < 30; i++) {
            const bar = document.createElement('div');
            bar.className = 'viz-bar';
            bar.style.height = '2px';
            micViz.appendChild(bar);
        }
        const vizBars = micViz.querySelectorAll('.viz-bar');

        function updateMicViz() {
            if (!micAnalyser) return;
            const data = new Uint8Array(micAnalyser.frequencyBinCount);
            micAnalyser.getByteFrequencyData(data);
            const step = Math.floor(data.length / vizBars.length);
            for (let i = 0; i < vizBars.length; i++) {
                const val = data[i * step];
                const pct = Math.max(2, (val / 255) * 60);
                vizBars[i].style.height = pct + 'px';
            }
            micRaf = requestAnimationFrame(updateMicViz);
        }

        btnMic.addEventListener('click', async () => {
            try {
                micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                micStatus.textContent = '权限被拒绝';
                micStatus.className = 'status status-error';
                micError.style.display = 'block';
                micError.textContent = '请在浏览器地址栏点击 🔒 图标，允许麦克风权限后刷新页面';
                return;
            }
            micError.style.display = 'none';
            recordedChunks = [];
            mediaRecorder = new MediaRecorder(micStream);
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) recordedChunks.push(e.data);
            };
            mediaRecorder.onstop = () => {
                const blob = new Blob(recordedChunks, { type: 'audio/webm' });
                const url = URL.createObjectURL(blob);
                playbackAudio.src = url;
                playbackAudio.style.display = 'block';
                btnPlayback.disabled = false;
                micStatus.textContent = '✅ 录制完成';
                micStatus.className = 'status status-done';
                if (micAudioCtx) {
                    micAudioCtx.close();
                    micAudioCtx = null;
                }
                if (micRaf) cancelAnimationFrame(micRaf);
                vizBars.forEach(b => b.style.height = '2px');
            };

            micAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            micSource = micAudioCtx.createMediaStreamSource(micStream);
            micAnalyser = micAudioCtx.createAnalyser();
            micAnalyser.fftSize = 256;
            micSource.connect(micAnalyser);
            updateMicViz();

            mediaRecorder.start();
            micStatus.textContent = '🔴 录制中...';
            micStatus.className = 'status status-playing';
            btnMic.disabled = true;

            setTimeout(() => {
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                    micStream.getTracks().forEach(t => t.stop());
                    btnMic.disabled = false;
                }
            }, 3000);
        });

        btnPlayback.addEventListener('click', () => {
            playbackAudio.play();
        });

        // ===== 摄像头测试 =====
        const btnCamOpen = document.getElementById('btn-cam-open');
        const btnSnapshot = document.getElementById('btn-snapshot');
        const btnCamClose = document.getElementById('btn-cam-close');
        const camVideo = document.getElementById('cam-video');
        const camStatus = document.getElementById('cam-status');
        const snapshotContainer = document.getElementById('snapshot-container');
        const camError = document.getElementById('cam-error');
        let camStream = null;

        btnCamOpen.addEventListener('click', async () => {
            try {
                camStream = await navigator.mediaDevices.getUserMedia({ video: true });
            } catch (err) {
                camStatus.textContent = '权限被拒绝';
                camStatus.className = 'status status-error';
                camError.style.display = 'block';
                camError.textContent = '请在浏览器地址栏点击 🔒 图标，允许摄像头权限后刷新页面';
                return;
            }
            camError.style.display = 'none';
            camVideo.srcObject = camStream;
            camVideo.style.display = 'block';
            camStatus.textContent = '📹 摄像头已打开';
            camStatus.className = 'status status-playing';
            btnCamOpen.disabled = true;
            btnSnapshot.disabled = false;
            btnCamClose.disabled = false;
        });

        btnSnapshot.addEventListener('click', () => {
            const canvas = document.createElement('canvas');
            canvas.width = camVideo.videoWidth || 640;
            canvas.height = camVideo.videoHeight || 480;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(camVideo, 0, 0, canvas.width, canvas.height);
            const img = document.createElement('img');
            img.src = canvas.toDataURL('image/png');
            img.className = 'snapshot-preview';
            snapshotContainer.appendChild(img);
            camStatus.textContent = '📸 截图已保存';
            camStatus.className = 'status status-done';
        });

        btnCamClose.addEventListener('click', () => {
            if (camStream) {
                camStream.getTracks().forEach(t => t.stop());
                camStream = null;
            }
            camVideo.srcObject = null;
            camVideo.style.display = 'none';
            camStatus.textContent = '⏹️ 摄像头已关闭';
            camStatus.className = 'status status-waiting';
            btnCamOpen.disabled = false;
            btnSnapshot.disabled = true;
            btnCamClose.disabled = true;
        });
    })();
    </script>
</body>
</html>
'''


@app.route('/test')
def test_page():
    return render_template_string(test_page_html)


@app.route('/assets/<path:path>')
def serve_static(path):  # 静态资源
    return send_from_directory('./dist/assets', path)


@app.route('/api/sessions/new', methods=['POST'])
def api_sessions_new():
    """新建会话

    Response:
        {"status": "success", "id": "...", "title": "", ...}
    """
    try:
        session_id = create_session()
        session = get_session(session_id)
        return jsonify({
            'status': 'success',
            'id': session_id,
            'title': session['title'],
            'created_at': session['created_at'],
            'updated_at': session['updated_at'],
            'message_count': session['message_count'],
            'is_archived': session['is_archived'],
            'messages': [],
        })
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_new 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions', methods=['GET'])
def api_sessions_list():
    """获取会话列表

    Response:
        {"status": "success", "sessions": [...]}
    """
    try:
        sessions = list_sessions(limit=100)
        return jsonify({'status': 'success', 'sessions': sessions})
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_list 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions/<session_id>', methods=['GET'])
def api_sessions_detail(session_id: str):
    """获取单个会话详情

    Response:
        {"status": "success", "id": "...", "messages": [...]}
    """
    try:
        from archive import restore_session
        session = get_session(session_id)
        if not session:
            return jsonify({'status': 'error', 'message': '会话不存在'})

        # 如已归档，先恢复
        if session.get('is_archived'):
            restored = restore_session(session_id)
            if not restored:
                return jsonify({
                    'status': 'error',
                    'message': '归档会话恢复失败',
                    'id': session_id,
                })
            session = get_session(session_id)

        messages = get_session_messages(session_id, limit=100)
        return jsonify({
            'status': 'success',
            'id': session_id,
            'title': session['title'],
            'created_at': session['created_at'],
            'updated_at': session['updated_at'],
            'message_count': session['message_count'],
            'is_archived': session['is_archived'],
            'messages': messages,
        })
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_detail 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def api_sessions_delete(session_id: str):
    """删除会话（级联删除音频缓存）"""
    try:
        from archive import delete_archive_file
        from conversation import delete_session
        from tts import delete_session_audio
        # 先删归档文件（如有）
        delete_archive_file(session_id)
        # 级联删除音频缓存
        try:
            delete_session_audio(session_id)
        except Exception:
            logging.getLogger("web_state").exception(f"删除会话音频缓存失败: {session_id}")
        # 再删会话（CASCADE 删消息 + 删目录）
        deleted = delete_session(session_id)
        if deleted:
            return jsonify({'status': 'success', 'message': '会话已删除'})
        else:
            return jsonify({'status': 'error', 'message': '会话不存在'})
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_delete 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions/<session_id>', methods=['PUT'])
def api_sessions_rename(session_id: str):
    """重命名会话

    Request:
        {"title": "新标题"}
    """
    try:
        from conversation import update_session_title
        data = request.json
        title = data.get('title', '')
        updated = update_session_title(session_id, title)
        if updated:
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': '会话不存在'})
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_rename 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions/<session_id>/save', methods=['POST'])
def api_sessions_save(session_id: str):
    """前端兜底保存接口（带乐观锁）

    Request:
        {"messages": [{"role": "...", "content": "...", ...}], "expected_updated_at": 1714675800}
    """
    try:
        data = request.json
        messages = data.get('messages', [])
        expected_updated_at = data.get('expected_updated_at')
        result = update_session_with_lock(session_id, messages, expected_updated_at)
        return jsonify(result)
    except Exception as e:
        logging.getLogger("web_state").error("api_sessions_save 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/sessions/<session_id>/images/<filename>')
def api_session_image(session_id: str, filename: str):
    """提供会话图片文件"""
    directory = os.path.join('data', 'sessions', session_id, 'images')
    if not os.path.exists(directory):
        return jsonify({'status': 'error', 'message': '图片不存在'})
    return send_from_directory(directory, filename)


@app.route('/api/sessions/<session_id>/files/<filename>')
def api_session_file(session_id: str, filename: str):
    """提供会话附件文件"""
    directory = os.path.join('data', 'sessions', session_id, 'files')
    if not os.path.exists(directory):
        return jsonify({'status': 'error', 'message': '文件不存在'})
    return send_from_directory(directory, filename)


@app.route('/api/archive/run', methods=['POST'])
def api_archive_run():
    """手动触发归档扫描"""
    try:
        result = archive_old_sessions()
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logging.getLogger("web_state").error("api_archive_run 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/get_config', methods=['GET'])
def api_get_config():
    """获取当前配置（供聊天页读取 llm_preset 等）"""
    try:
        cfg = load_config()
        return jsonify(cfg)
    except Exception as e:
        logging.getLogger("web_state").error("api_get_config 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/parse_file', methods=['POST'])
def api_parse_file():
    """接收前端上传的文件，解析为文本后返回"""
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': '未上传文件'})

        file = request.files['file']
        if not file.filename:
            return jsonify({'status': 'error', 'message': '文件名为空'})

        # 检查依赖
        deps = check_dependencies()
        ext = os.path.splitext(file.filename)[1].lower()
        if ext == '.pdf' and not deps['pdfplumber']:
            return jsonify({'status': 'error', 'message': '请安装 pdfplumber: pip install pdfplumber'})
        if ext == '.docx' and not deps['python-docx']:
            return jsonify({'status': 'error', 'message': '请安装 python-docx: pip install python-docx'})

        # 保存到临时目录
        temp_dir = 'data/cache'
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)

        try:
            text, truncated = parse_file(temp_path)
            if not text.strip() and ext == '.pdf':
                return jsonify({'status': 'error', 'message': '该 PDF 为扫描件，无法提取文本'})

            return jsonify({
                'status': 'success',
                'text': text,
                'truncated': truncated,
                'filename': file.filename
            })
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logging.getLogger("web_state").error("api_parse_file 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/save_preset', methods=['POST'])
def api_save_preset():
    """保存 LLM 预设参数或模型配置（供聊天页快捷切换）"""
    try:
        data = request.get_json() or {}
        preset = data.get('preset')
        openai_llm_model = data.get('openai_llm_model')
        openai_vlm_model = data.get('openai_vlm_model')

        cfg = load_config()

        if preset:
            presets = {
                "balanced": {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.9},
                "analysis": {"temperature": 0.3, "max_tokens": 8192, "top_p": 0.5},
                "creative": {"temperature": 0.95, "max_tokens": 4096, "top_p": 1.0},
            }
            cfg['llm_params'] = presets.get(preset, presets["balanced"]).copy()
            cfg['llm_preset'] = preset

        if openai_llm_model is not None:
            cfg['openai_llm_model'] = openai_llm_model
        if openai_vlm_model is not None:
            cfg['openai_vlm_model'] = openai_vlm_model

        if save_config(cfg):
            return jsonify({'status': 'success', 'preset': preset})
        return jsonify({'status': 'error', 'message': '保存配置失败'})
    except Exception as e:
        logging.getLogger("web_state").error("api_save_preset 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)})


@app.route("/api/openai_models", methods=["GET"])
def api_openai_models():
    """获取 OpenAI 兼容服务的模型列表（供聊天页调用）"""
    try:
        base_url = request.args.get("base_url", openai_url)
        api_key = request.args.get("api_key", openai_key)

        if not base_url:
            return jsonify({"status": "error", "message": "未配置 OpenAI 地址"})

        # 绕开 openai 包（避免 zhipuai monkey-patch 冲突），直接用 requests 调 /v1/models
        import requests as rq
        url = base_url.rstrip('/') + '/models'
        headers = {"Authorization": f"Bearer {api_key or 'no-key'}"}
        resp = rq.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        model_ids = [m["id"] for m in data.get("data", []) if "id" in m]
        model_ids.sort()

        return jsonify({"status": "success", "models": model_ids})

    except Exception as e:
        logging.getLogger("web_state").error("获取模型列表失败", exc_info=True)
        return jsonify({"status": "error", "message": f"无法获取模型列表: {str(e)}"})


@app.route("/api/vlm_stream", methods=["POST"])
def handle_vlm_stream():
    """SSE 流式 VLM 接口（仅处理含图片的消息）

    Request: JSON {"message": "...", "session_id": "...", "image_base64": "..."}
    Response: text/event-stream
      data: {"type": "token", "content": "..."}\n\n
      data: {"type": "done", "full_text": "..."}\n\n
      data: {"type": "error", "message": "..."}\n\n

    注意：纯文本消息不走此接口，前端直接调用同步 /api/chat。
    done 事件中携带 full_text，便于前端直接回传保存。
    """
    def generate():
        try:
            data = request.get_json() or {}
            message = data.get("message", "")
            session_id = data.get("session_id", "")
            image_base64 = data.get("image_base64")

            # 无图片时返回错误
            if not image_base64:
                yield f'data: {json.dumps({"type": "error", "message": "仅支持图片消息流式处理"})}\n\n'
                return

            # 1. 检查/创建会话
            if not session_id:
                session_id = create_session()
            else:
                session = get_session(session_id)
                if not session:
                    session_id = create_session()

            # 2. 保存图片到文件系统
            image_path = _save_base64_image(session_id, image_base64)

            # 3. 保存用户消息到 SQLite
            save_message(session_id, "user", content=message, image_path=image_path)

            # 4. 更新会话消息计数
            session_messages = get_session_messages(session_id, limit=20)
            new_count = len(session_messages)
            update_session_message_count(session_id, new_count)

            # 图片缓存检查
            from vlm import _get_image_hash, _get_cached_image_analysis, _set_cached_image_analysis, _build_vlm_messages, _vlm_completion_stream
            image_hash = _get_image_hash(image_base64)
            cached = _get_cached_image_analysis(session_id, image_hash)
            if cached:
                # 缓存命中：直接返回 done
                yield f'data: {json.dumps({"type": "token", "content": cached})}\n\n'
                yield f'data: {json.dumps({"type": "done", "full_text": cached})}\n\n'
                return

            # 构建 messages
            messages = _build_vlm_messages(message, image_base64)

            # 获取当前 VLM 引擎配置
            current_vlm = get_config_value("prefer_vlm", prefer_vlm)
            if current_vlm == "off" or not current_vlm:
                yield f'data: {json.dumps({"type": "error", "message": "VLM 未启用"})}\n\n'
                return

            # VLM 流式调用（含后端降级）
            full_text = ""
            for token in _vlm_completion_stream(current_vlm, messages):
                full_text += token
                yield f'data: {json.dumps({"type": "token", "content": token})}\n\n'

            # 保存到缓存
            _set_cached_image_analysis(session_id, image_hash, full_text)

            # 发送 done 事件
            yield f'data: {json.dumps({"type": "done", "full_text": full_text})}\n\n'

        except Exception as e:
            logging.getLogger("web_state").error(f"/api/vlm_stream 异常: {e}", exc_info=True)
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route('/api/search', methods=['POST'])
def api_search():
    """全局搜索消息内容

    Request: JSON {"q": "关键词"}
    Response: {"status": "success", "results": [...], "total": N, "has_more": false}
    """
    try:
        data = request.get_json() or {}
        keyword = data.get('q', '').strip()

        if not keyword:
            return jsonify({'status': 'success', 'results': [], 'total': 0, 'has_more': False})

        if len(keyword) > 100:
            return jsonify({'status': 'error', 'message': '关键词过长（最多 100 字）'})

        results = search_messages(keyword, limit=51)
        total = sum(len(g['matches']) for g in results)
        has_more = total > 50
        if has_more:
            # 按匹配数截断到 50 条（从最后一个分组开始移除）
            remaining = 50
            truncated = []
            for g in results:
                if remaining <= 0:
                    break
                if len(g['matches']) <= remaining:
                    truncated.append(g)
                    remaining -= len(g['matches'])
                else:
                    truncated.append({
                        **g,
                        'matches': g['matches'][:remaining]
                    })
                    remaining = 0
            results = truncated
            total = 50

        return jsonify({
            'status': 'success',
            'results': results,
            'total': total,
            'has_more': has_more
        })

    except Exception as e:
        logging.getLogger("web_state").error("api_search 异常", exc_info=True)
        return jsonify({'status': 'error', 'message': '搜索失败，请重试'})


def run_state_web():  # 启动主机状态监测服务
    print(f"主机状态网址：http://{lan_ip}:{str(state_port)}\n")
    app.run(port=state_port, host="0.0.0.0")
