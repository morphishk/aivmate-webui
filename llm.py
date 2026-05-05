from tts import stop_tts
from datetime import datetime
from vlm import glm_4v_cam, openai_vlm_cam, ollama_vlm_cam, lmstudio_vlm_cam, yolo_ocr_cam
from web_settings import (
    get_config_value, get_config, get_llm_client,
    prefer_llm, prefer_vlm, prefer_tts, mate_name, username, prompt,
    glm_key, glm_llm_model, openai_url, openai_key, openai_llm_model,
    ollama_url, ollama_llm_model, lmstudio_url, auto_optimize_memory_switch,
    dify_key, dify_ip, anything_llm_ip, anything_llm_ws, anything_llm_key,
    rkllm_url, get_llm_params, _cast_param_value, _filter_params
)
from function import (
    get_weather, get_news, ol_search, get_wifi_info, get_lan_url,
    get_wan_info, get_state, control_ha, input_face, delete_face,
    recognize_face, switch_asr_mode, switch_ase_mode, exit_app, reboot, shutdown
)
from zai import ZhipuAiClient
from openai import OpenAI, AuthenticationError, PermissionDeniedError, APIError
import json
import os
import random
import subprocess
import requests as rq
import logging

# ============================================================
# 两条消息处理路径（P1 新增，明确隔离）：
#
# 路径 1（本地语音模式）: chat_preprocess() -> chat_llm()
#    - 使用全局 openai_history + data/db/memory.db
#    - 供 sense_voice_main() / run_ase() / text_chat() 调用
#    - P1 不修改此路径，保持原有行为
#
# 路径 2（Web 聊天模式）:  handle_chat() -> chat_with_history()
#    - 使用会话隔离的聊天记录 + data/db/conversations.db
#    - 供 web_state.py /api/chat 调用
#    - P1 新增此路径
# ============================================================

try:
    with open('data/db/memory.db', 'r', encoding='utf-8') as memory_file:
        openai_history = json.load(memory_file)
except (FileNotFoundError, json.JSONDecodeError):
    openai_history = []
    os.makedirs('data/db', exist_ok=True)


_LLM_PARAM_SCHEMA = {
    "ZhipuAI": ["temperature", "max_tokens"],
    "OpenAI": ["temperature", "max_tokens", "top_p"],
    "Ollama": ["temperature"],
    "LM Studio": ["temperature", "max_tokens", "top_p"],
}


def _filter_params_for_engine(params: dict, engine_name: str) -> dict:
    """根据引擎白名单过滤参数，不支持的参数静默忽略
    
    Args:
        params: 原始参数字典（来自 config.json）
        engine_name: 引擎名称
        
    Returns:
        dict: 过滤后的参数，仅包含该引擎支持的键
    """
    return _filter_params(params, engine_name, _LLM_PARAM_SCHEMA)


def current_time():  # 当前时间
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _extract_last_user_msg(messages: list[dict]) -> str:
    """从消息数组中提取最后一条 user 消息的 content

    Args:
        messages: OpenAI 格式的消息数组

    Returns:
        str: 最后一条 user 消息的 content，不存在则返回空字符串
    """
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _get_llm_model_name(engine_name: str) -> str:
    """实时读取当前配置的模型名"""
    cfg = get_config()
    mapping = {
        "ZhipuAI": cfg.get("glm_llm_model", glm_llm_model),
        "OpenAI": cfg.get("openai_llm_model", openai_llm_model),
        "Ollama": cfg.get("ollama_llm_model", ollama_llm_model),
        "LM Studio": "",
    }
    return mapping.get(engine_name, "")


def _call_llm_with_messages(messages: list[dict]) -> str:
    """根据 prefer_llm 调用对应引擎，传入完整的 messages 数组

    Args:
        messages: OpenAI 格式的消息数组（含 system prompt）

    Returns:
        str: assistant 回复文本
    """
    engine = get_config_value("prefer_llm", prefer_llm)
    params = _filter_params_for_engine(get_llm_params(), engine)
    model = _get_llm_model_name(engine)
    if engine == "ZhipuAI":
        client = get_llm_client("ZhipuAI")
        completion = client.chat.completions.create(
            model=model, messages=messages, thinking={"type": "disabled"},
            timeout=120, **params
        )
        return completion.choices[0].message.content.strip()
    elif engine == "OpenAI":
        client = get_llm_client("OpenAI")
        completion = client.chat.completions.create(
            model=model, messages=messages, timeout=120, **params
        )
        return completion.choices[0].message.content.strip()
    elif engine == "Ollama":
        cfg = get_config()
        url = cfg.get("ollama_url", ollama_url)
        try:
            rq.get(url.replace("/v1", ""), timeout=5)
        except (rq.ConnectionError, rq.Timeout):
            subprocess.run(["ollama", "pull", model], timeout=120, check=False)
        client = get_llm_client("Ollama")
        completion = client.chat.completions.create(
            model=model, messages=messages, timeout=120, **params
        )
        return completion.choices[0].message.content
    elif engine == "LM Studio":
        client = get_llm_client("LM Studio")
        completion = client.chat.completions.create(
            model="", messages=messages, timeout=120, **params
        )
        return completion.choices[0].message.content.strip()
    elif engine == "AnythingLLM":
        # AnythingLLM 不支持 messages 数组格式，fallback 到单条消息
        user_msg = _extract_last_user_msg(messages)
        return chat_anything_llm(user_msg) if user_msg else "消息为空"
    elif engine == "Dify":
        user_msg = _extract_last_user_msg(messages)
        return chat_dify(user_msg) if user_msg else "消息为空"
    elif engine == "RKLLM":
        user_msg = _extract_last_user_msg(messages)
        return chat_rkllm(user_msg) if user_msg else "消息为空"
    else:
        return "对话语言模型选择错误，请检查配置"


def _truncate_messages(messages: list[dict], max_chars: int = 6000) -> list[dict]:
    """从最早的用户消息开始截断，保留 system prompt 和最近消息

    保守策略：中文 1 字符约相当于 1.5 token，6000 字符约 9000 tokens。
    此估算对中文偏乐观，实际运行后根据模型反馈调优。

    Args:
        messages: 完整消息数组（含 system prompt 在首位）
        max_chars: 最大字符数（默认 6000）

    Returns:
        list[dict]: 截断后的消息数组
    """
    if not messages:
        return messages

    total_chars = sum(len(m.get("content", "")) for m in messages)
    if total_chars <= max_chars:
        return messages

    # 保留 system prompt（messages[0] 假设为 system）
    result = [messages[0]] if messages[0].get("role") == "system" else []
    system_len = len(result[0].get("content", "")) if result else 0
    remaining = max_chars - system_len

    # 从后往前取消息，直到剩余空间不足
    source_messages = messages[1:] if result else messages
    for m in reversed(source_messages):
        msg_len = len(m.get("content", ""))
        if remaining >= msg_len:
            result.insert(1 if result else 0, m)
            remaining -= msg_len
        else:
            break

    return result


def chat_with_history(
    msg: str, session_messages: list[dict], system_prompt: str | None = None
) -> str:
    """路径 2：Web 聊天模式，接收当前消息 + 会话历史，不读写全局 openai_history

    Args:
        msg: 当前用户消息文本
        session_messages: 该会话的历史消息数组（OpenAI 格式，不含 system）
        system_prompt: 可选的系统提示词，覆盖默认

    Returns:
        str: assistant 回复文本
    """
    # 1. 构建 messages 数组
    messages = []
    current_prompt = system_prompt if system_prompt else get_config_value("prompt", prompt)
    messages.append({"role": "system", "content": current_prompt})

    # 2. 追加会话历史（已截断）
    truncated = _truncate_messages(session_messages, max_chars=6000)
    messages.extend(truncated)

    # 3. 追加当前用户消息
    messages.append({"role": "user", "content": msg})

    # 4. 调用 LLM API
    response = _call_llm_with_messages(messages)

    return response


def chat_llm(msg):  # 与大语言模型对话（路径 1：本地语音模式）
    """路径 1：本地语音模式，维护全局 openai_history

    P1 保持原有行为不变，供 sense_voice_main() / run_ase() / text_chat() 调用。
    P2 新增：传入 llm_params 参数。
    P3 新增：实时读取配置，支持热更新。
    """
    engine = get_config_value("prefer_llm", prefer_llm)
    params = _filter_params_for_engine(get_llm_params(), engine)
    model = _get_llm_model_name(engine)
    current_prompt = get_config_value("prompt", prompt)

    if engine == "ZhipuAI":
        client = get_llm_client("ZhipuAI")
        openai_history.append({"role": "user", "content": msg})
        messages = [{"role": "system", "content": current_prompt}]
        messages.extend(openai_history)
        completion = client.chat.completions.create(model=model, messages=messages,
                                                        thinking={"type": "disabled"}, timeout=120, **params)
        openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
        return completion.choices[0].message.content.strip()
    elif engine == "OpenAI":
        client = get_llm_client("OpenAI")
        openai_history.append({"role": "user", "content": msg})
        messages = [{"role": "system", "content": current_prompt}]
        messages.extend(openai_history)
        completion = client.chat.completions.create(model=model, messages=messages, timeout=120, **params)
        openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
        return completion.choices[0].message.content.strip()
    elif engine == "Ollama":
        cfg = get_config()
        url = cfg.get("ollama_url", ollama_url)
        try:
            rq.get(url.replace("/v1", ""), timeout=5)
        except (rq.ConnectionError, rq.Timeout):
            subprocess.run(["ollama", "pull", model], timeout=120, check=False)
        client = get_llm_client("Ollama")
        openai_history.append({"role": "user", "content": msg})
        messages = [{"role": "system", "content": current_prompt}]
        messages.extend(openai_history)
        completion = client.chat.completions.create(model=model, messages=messages, timeout=120, **params)
        openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
        return completion.choices[0].message.content
    elif engine == "LM Studio":
        client = get_llm_client("LM Studio")
        openai_history.append({"role": "user", "content": msg})
        messages = [{"role": "system", "content": current_prompt}]
        messages.extend(openai_history)
        completion = client.chat.completions.create(model="", messages=messages, timeout=120, **params)
        openai_history.append({"role": "assistant", "content": completion.choices[0].message.content})
        return completion.choices[0].message.content.strip()
    elif engine == "AnythingLLM":
        res = chat_anything_llm(msg)
        return res
    elif engine == "Dify":
        res = chat_dify(msg)
        return res
    elif engine == "RKLLM":
        res = chat_rkllm(msg)
        return res
    else:
        return "对话语言模型选择错误，请检查配置"


def chat_preprocess(msg, image_base64=None, prev_image_base64=None, file_content=None, file_name=None):  # 对话预处理
    stop_tts()
    try:
        if "几点" in msg or "多少点" in msg or "时间" in msg or "时候" in msg or "日期" in msg or "多少号" in msg or "几号" in msg:
            msg = f"[当前时间:{current_time()}]{msg}"
        if "哈喽" in msg:
            current_username = get_config_value("username", username)
            current_mate_name = get_config_value("mate_name", mate_name)
            res = f"{current_username}，我是{current_mate_name}，很高兴遇见你"
        elif "唱一" in msg or "唱首" in msg or "唱歌" in msg or "放歌" in msg or "放一" in msg or "放首" in msg or "你唱" in msg or "跳舞" in msg:
            res = "音乐播放功能暂未开放，我可以陪你聊天哦"
        # ===== 关键修复：只要有图片，优先走 VLM 分支 =====
        elif image_base64 and get_config_value("prefer_vlm", prefer_vlm) != "off":
            # 用户传了图片，调用 VLM 分析（支持多图对比）
            current_vlm = get_config_value("prefer_vlm", prefer_vlm)
            if current_vlm == "ZhipuAI":
                res = glm_4v_cam(msg, image_base64=image_base64, prev_image_base64=prev_image_base64)
            elif current_vlm == "OpenAI":
                res = openai_vlm_cam(msg, image_base64=image_base64, prev_image_base64=prev_image_base64)
            elif current_vlm == "Ollama":
                res = ollama_vlm_cam(msg, image_base64=image_base64, prev_image_base64=prev_image_base64)
            elif current_vlm == "LM Studio":
                res = lmstudio_vlm_cam(msg, image_base64=image_base64, prev_image_base64=prev_image_base64)
            elif current_vlm == "YOLO-OCR":
                res = yolo_ocr_cam(msg, image_base64=image_base64, prev_image_base64=prev_image_base64)
            else:
                res = "图像识别引擎选择错误，请检查配置"
        elif (
                "画面" in msg or "图像" in msg or "看到" in msg or "看看" in msg or "看见" in msg or "照片" in msg or "摄像头" in msg or "图片" in msg or
                "图" in msg or "图里" in msg or "图上" in msg or "图中" in msg or "这张" in msg or "画像" in msg or "截图" in msg or "相片" in msg or
                "拍的照片" in msg or "刚才的图" in msg or "这张图片" in msg) and get_config_value("prefer_vlm", prefer_vlm) != "off":
            # 消息包含视觉关键词但没有附带图片，返回引导语
            res = "我可以识别图片内容！您可以点击输入框旁的 🎥 按钮拍照，或上传本地图片让我查看~"
        elif "天气" in msg:
            res = get_weather(msg)
        elif "新闻" in msg:
            res = get_news(msg)
        elif "联网" in msg or "连网" in msg or "搜索" in msg or "查询" in msg or "查找" in msg:
            res = ol_search(msg)
        elif "信号" in msg or "强度" in msg:
            res = get_wifi_info()
        elif "网址" in msg or "地址" in msg or "端口" in msg:
            res = get_lan_url()
        elif "网络" in msg:
            res = get_wan_info()
        elif "状态" in msg or "温度" in msg:
            res = get_state()
        elif "灯" in msg and "开" in msg:
            res = control_ha()
        elif "灯" in msg and "关" in msg:
            res = control_ha()
        elif "录入人脸" in msg:
            res = input_face(msg)
        elif "删除人脸" in msg:
            res = delete_face()
        elif "我是谁" in msg:
            res = recognize_face()
            if "未检测到摄像头" in res or "摄像头画面读取失败" in res or "摄像头访问异常" in res:
                res = "我还不知道你的名字呢，可以告诉我怎么称呼你吗？"
        elif "切换" in msg and "语音" in msg:
            res = switch_asr_mode()
        elif "切换" in msg and "主动" in msg:
            res = switch_ase_mode()
        elif "设置" in msg or "配置" in msg or "模式" in msg:
            with open("data/db/current_asr.txt", "r", encoding="utf-8") as f:
                current_asr = f.read()
            with open("data/db/current_ase.txt", "r", encoding="utf-8") as f:
                current_ase = f.read()
            current_prefer_llm = get_config_value("prefer_llm", prefer_llm)
            current_prefer_tts = get_config_value("prefer_tts", prefer_tts)
            current_prefer_vlm = get_config_value("prefer_vlm", prefer_vlm)
            res = f"语音识别模式为{current_asr}，对话语言模型为{current_prefer_llm}，语音合成引擎为{current_prefer_tts}，图像识别引擎为{current_prefer_vlm}，主动感知对话为{current_ase}"
        elif "确认删除记忆" in msg or "确定删除记忆" in msg:
            res = clear_chat()
        elif "确定退出" in msg or "确认退出" in msg:
            exit_app()
            return None
        elif "确认重新启动" in msg or "确定重新启动" in msg:
            reboot()
            return None
        elif "确认关机" in msg or "确定关机" in msg:
            shutdown()
            return None
        else:
            # 在所有关键词判断完成后，如果有文件内容，再附加到消息中传给 LLM
            if file_content and file_name:
                msg = f"[文件: {file_name}]\n{file_content}\n\n用户说: {msg}"
            res = chat_llm(msg)
        if get_config_value("auto_optimize_memory_switch", auto_optimize_memory_switch) == "on":
            current_rounds = len(openai_history) // 2
            if current_rounds > 50:
                round_to_remove = random.randint(0, current_rounds - 1) * 2
                del openai_history[round_to_remove:round_to_remove + 2]
        os.makedirs('data/db', exist_ok=True)
        with open('data/db/memory.db', 'w', encoding='utf-8') as f:
            json.dump(openai_history, f, ensure_ascii=False, indent=4)
    except (AuthenticationError, PermissionDeniedError):
        res = "API 密钥无效或权限不足，请检查系统设置中的密钥配置"
        logging.getLogger('llm').error("API认证异常", exc_info=True)
    except APIError:
        res = "AI 服务返回错误，请稍后重试"
        logging.getLogger('llm').error("AI服务异常", exc_info=True)
    except (rq.Timeout, TimeoutError):
        res = "请求超时，请检查网络连接"
        logging.getLogger('llm').error("请求超时", exc_info=True)
    except (rq.ConnectionError, ConnectionError):
        res = "网络连接失败，请检查服务是否可用"
        logging.getLogger('llm').error("网络异常", exc_info=True)
    except (KeyError, IndexError) as e:
        res = f"数据解析错误：{e}"
        logging.getLogger('llm').error("数据解析异常", exc_info=True)
    except Exception as e:
        res = f"服务异常：{e}"
        logging.getLogger('llm').error("未知异常", exc_info=True)
    res = res.replace("#", "").replace("*", "")
    current_mate_name = get_config_value("mate_name", mate_name)
    print(f"{current_mate_name}：{res}")
    # WebUI 模式下由前端播放 TTS；本地/语音模式仍调用 play_tts_legacy
    # 此处不再直接播放，交由调用方决定
    return res


# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
def chat_dify(msg):  # Dify知识库
    cfg = get_config()
    key = cfg.get("dify_key", dify_key)
    ip = cfg.get("dify_ip", dify_ip)
    user = cfg.get("username", username)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"query": msg, "inputs": {}, "response_mode": "blocking", "user": user, "conversation_id": None}
    res = rq.post(f"{ip}/v1/chat-messages", headers=headers, data=json.dumps(data))
    res = res.json()['answer'].strip()
    return res


def chat_anything_llm(msg):  # AnythingLLM知识库
    cfg = get_config()
    ip = cfg.get("anything_llm_ip", anything_llm_ip)
    ws = cfg.get("anything_llm_ws", anything_llm_ws)
    key = cfg.get("anything_llm_key", anything_llm_key)
    url = f"{ip}/api/v1/workspace/{ws}/chat"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"message": msg, "mode": "chat"}
    res = rq.post(url, json=data, headers=headers)
    return res.json().get("textResponse")


def chat_rkllm(msg):  # RKLLM
    cfg = get_config()
    url = cfg.get("rkllm_url", rkllm_url)
    res = rq.get(f"{url}/rkllm?msg={msg}")
    res = res.json()['answer'].strip()
    return res


def clear_chat():  # 删除记忆
    global openai_history
    openai_history = []
    os.makedirs('data/db', exist_ok=True)
    with open('data/db/memory.db', 'w', encoding='utf-8') as f:
        f.write("")
    return "记忆已清空"
