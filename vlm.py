import os
import subprocess
import cv2
import json
import requests as rq
from rapidocr_openvino import RapidOCR
from ultralytics import YOLO
from llm_client import OpenAICompatibleClient
from web_settings import (
    get_config_value, get_llm_params, _filter_params,
    glm_key, glm_vlm_model, ollama_url, ollama_vlm_model,
    lmstudio_url, openai_url, openai_key, openai_vlm_model, ollama_llm_model,
)
import numpy as np
from base64 import b64decode
from zai import ZhipuAiClient
from typing import Any
from collections import OrderedDict
import hashlib

cls_model, det_model, ocr = None, None, None
vlm_prompt = None  # will be set after web_settings imports

# session_id -> {image_hash: analysis_text}
# LRU 策略：OrderedDict，命中时 move_to_end，超限时 popitem(last=False)
_vlm_image_cache: dict[str, OrderedDict[str, str]] = {}
_VLM_CACHE_MAX_IMAGES = 10  # 每会话最多缓存 10 张图片的分析结果


_VLM_PARAM_SCHEMA = {
    "ZhipuAI": ["temperature"],
    "OpenAI": ["temperature", "max_tokens", "top_p"],
    "Ollama": ["temperature"],
    "LM Studio": ["temperature", "max_tokens", "top_p"],
}


def _filter_vlm_params(params: dict, engine_name: str) -> dict:
    """VLM 参数过滤（通常比 LLM 支持更少）
    
    Args:
        params: 原始参数字典
        engine_name: 引擎名称
        
    Returns:
        dict: 过滤后的参数
    """
    return _filter_params(params, engine_name, _VLM_PARAM_SCHEMA)


VLM_CONFIG: dict[str, dict[str, Any]] = {
    "ZhipuAI": {
        "client_builder": lambda: ZhipuAiClient(
            api_key=get_config_value("glm_key", glm_key)
        ),
        "model": lambda: get_config_value("glm_vlm_model", glm_vlm_model),
        "extra_params": {"thinking": {"type": "disabled"}},
        "supports_streaming": False,
    },
    "OpenAI": {
        "client_builder": lambda: OpenAICompatibleClient(
            base_url=get_config_value("openai_url", openai_url),
            api_key=get_config_value("openai_key", openai_key)
        ),
        "model": lambda: get_config_value("openai_vlm_model", openai_vlm_model),
        "extra_params": {},
        "supports_streaming": True,
    },
    "Ollama": {
        "client_builder": lambda: OpenAICompatibleClient(
            base_url=get_config_value("ollama_url", ollama_url),
            api_key="ollama"
        ),
        "model": lambda: get_config_value("ollama_vlm_model", ollama_vlm_model),
        "extra_params": {},
        "supports_streaming": True,
    },
    "LM Studio": {
        "client_builder": lambda: OpenAICompatibleClient(
            base_url=get_config_value("lmstudio_url", lmstudio_url),
            api_key="lm-studio"
        ),
        "model": lambda: "",
        "extra_params": {},
        "supports_streaming": True,
    },
}


def _strip_base64_prefix(image_base64):
    """去除 data:image/xxx;base64, 前缀，返回纯 base64 字符串"""
    if image_base64.startswith('data:'):
        image_base64 = image_base64.split(',', 1)[-1]
    return image_base64


def _ensure_vlm_prompt():
    """延迟初始化 vlm_prompt，避免循环导入问题"""
    global vlm_prompt
    if vlm_prompt is None:
        from web_settings import prompt
        # VLM 场景下覆盖人设中的"简洁"约束，改为鼓励详细描述
        vlm_prompt = prompt.replace("回复尽量简洁，不要包含emoji，不要超过100字。", "请你仔细观察图片，尽可能详细、丰富地描述你看到的所有内容，可以展开细节和感受。") + "。你拥有图像识别能力"


def _build_vlm_messages(
    question: str,
    image_base64: str | None = None,
    prev_image_base64: str | None = None
) -> list[dict]:
    """构建 VLM 请求 messages 数组

    提取自现有 4 个函数的公共逻辑：
    1. 调用 _ensure_vlm_prompt() 获取 system prompt
    2. 构建 user message（含 image_url 和 text）
    3. 如有 prev_image_base64，追加前一张图片的上下文

    Args:
        question: 用户问题
        image_base64: 当前图片 base64（含 data:image 前缀或纯 base64）
        prev_image_base64: 前一张图片 base64（用于多图上下文）

    Returns:
        list[dict]: OpenAI 兼容 messages 格式
    """
    messages = []

    # system prompt
    _ensure_vlm_prompt()
    if vlm_prompt:
        messages.append({"role": "system", "content": vlm_prompt})

    # 构建 user message 内容
    content = [{"type": "text", "text": question}]

    # 前一张图片（多图上下文）
    if prev_image_base64:
        prev_base64 = _strip_base64_prefix(prev_image_base64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{prev_base64}"}
        })

    # 当前图片
    if image_base64:
        base64_image = _strip_base64_prefix(image_base64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        })

    messages.append({"role": "user", "content": content})
    return messages


def _vlm_completion(
    engine_name: str,
    messages: list[dict],
    stream: bool = False
) -> str:
    """调用 VLM 完成（统一封装各引擎差异）

    Args:
        engine_name: 引擎名称（ZhipuAI/OpenAI/Ollama/LM Studio）
        messages: _build_vlm_messages 返回的 messages 数组
        stream: 是否流式返回（仅 supports_streaming=True 的引擎支持）

    Returns:
        str: 同步模式下返回完整文本

    Raises:
        ValueError: 引擎名称不存在或不支持流式
        Exception: API 调用异常（透传原始异常）
    """
    config = VLM_CONFIG.get(engine_name)
    if not config:
        raise ValueError(f"未知 VLM 引擎: {engine_name}")

    if stream and not config["supports_streaming"]:
        raise ValueError(f"引擎 {engine_name} 不支持流式")

    # 构建客户端和模型
    client = config["client_builder"]()
    model = config["model"]()

    # 读取并过滤参数（复用 P2 的 _filter_vlm_params）
    params = get_llm_params()
    filtered = _filter_vlm_params(params, engine_name)

    # 合并 extra_params
    kwargs = {**config["extra_params"], **filtered}

    # 调用 API（同步模式）
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        timeout=120,
        **kwargs
    )

    msg = completion.choices[0].message
    # 兼容 reasoning_content 模型（如 kimi-for-coding）：content 为空时读取 reasoning_content
    return msg.content or (msg.reasoning_content if hasattr(msg, "reasoning_content") else None) or ""


def _vlm_completion_stream(engine_name: str, messages: list[dict]):
    """流式调用 VLM，yield 每个 token

    - 支持流式的引擎：正常 yield token
    - 不支持流式的引擎：后端降级为同步调用，作为单个 token yield

    Args:
        engine_name: 引擎名称
        messages: messages 数组

    Yields:
        str: 每个 token 文本片段
    """
    config = VLM_CONFIG.get(engine_name)
    if not config:
        raise ValueError(f"未知 VLM 引擎: {engine_name}")

    # 不支持流式的引擎：后端降级为同步单 token
    if not config["supports_streaming"]:
        result = _vlm_completion(engine_name, messages, stream=False)
        yield result
        return

    # 支持流式的引擎：正常 yield token
    client = config["client_builder"]()
    model = config["model"]()

    # 读取并过滤参数
    params = get_llm_params() if 'get_llm_params' in globals() else {}
    if '_filter_vlm_params' in globals():
        filtered = _filter_vlm_params(params, engine_name)
    else:
        filtered = params

    kwargs = {**config["extra_params"], **filtered}

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        timeout=120,
        **kwargs
    )

    # 策略：先缓存 thinking，遇到 content 后只输出 content
    # 避免前端先看到 thinking 再突然切换为 content
    thinking_buffer: list[str] = []
    content_started = False

    for chunk in completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue

        # content 优先级最高
        if delta.content:
            if not content_started:
                content_started = True
                thinking_buffer.clear()  # 丢弃前面的 thinking
            yield delta.content
            continue

        # 收集 thinking（仅在 content 未开始时）
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if not content_started:
                thinking_buffer.append(delta.reasoning_content)

    # 全程没有 content：fallback 输出 thinking
    if not content_started and thinking_buffer:
        for token in thinking_buffer:
            yield token


def _get_image_hash(image_base64: str) -> str:
    """计算图片 base64 的 SHA256 哈希（前 16 位）

    Args:
        image_base64: base64 编码的图片数据（可能包含 data URI 前缀）

    Returns:
        str: 16 位十六进制哈希字符串
    """
    # 去除可能的 data URI 前缀，仅对纯 base64 部分哈希
    pure_base64 = image_base64
    if pure_base64.startswith("data:"):
        pure_base64 = pure_base64.split(",", 1)[-1]
    return hashlib.sha256(pure_base64.encode("utf-8")).hexdigest()[:16]


def _get_cached_image_analysis(session_id: str, image_hash: str) -> str | None:
    """获取图片缓存的分析结果

    Args:
        session_id: 会话 ID
        image_hash: 图片哈希值

    Returns:
        str | None: 缓存的分析文本，无缓存返回 None
    """
    cache = _vlm_image_cache.get(session_id)
    if not cache:
        return None
    if image_hash in cache:
        # LRU：命中后移到末尾（最新）
        cache.move_to_end(image_hash)
        return cache[image_hash]
    return None


def _set_cached_image_analysis(session_id: str, image_hash: str, analysis: str) -> None:
    """缓存图片分析结果（LRU 策略）

    Args:
        session_id: 会话 ID
        image_hash: 图片哈希值
        analysis: VLM 分析结果文本
    """
    if session_id not in _vlm_image_cache:
        _vlm_image_cache[session_id] = OrderedDict()

    cache = _vlm_image_cache[session_id]
    cache[image_hash] = analysis
    cache.move_to_end(image_hash)

    # 超限淘汰最旧的
    while len(cache) > _VLM_CACHE_MAX_IMAGES:
        cache.popitem(last=False)


def glm_4v_cam(question, image_base64=None, prev_image_base64=None):
    """（兼容包装）ZhipuAI GLM-4V 视觉理解"""
    if not image_base64:
        return "请上传图片或点击摄像头按钮拍照，我才能看到画面内容哦~"
    messages = _build_vlm_messages(question, image_base64, prev_image_base64)
    return _vlm_completion("ZhipuAI", messages, stream=False)


def ollama_vlm_cam(question, image_base64=None, prev_image_base64=None):
    """（兼容包装）Ollama VLM"""
    if not image_base64:
        return "请上传图片或点击摄像头按钮拍照，我才能看到画面内容哦~"
    # Ollama 特有：服务可用性检查与自动拉取
    try:
        rq.get(ollama_url.replace("/v1", ""), timeout=5)
    except (rq.Timeout, rq.ConnectionError):
        subprocess.run(["ollama", "pull", ollama_vlm_model], timeout=120, check=False)
    messages = _build_vlm_messages(question, image_base64, prev_image_base64)
    return _vlm_completion("Ollama", messages, stream=False)


def lmstudio_vlm_cam(question, image_base64=None, prev_image_base64=None):
    """（兼容包装）LM Studio VLM"""
    if not image_base64:
        return "请上传图片或点击摄像头按钮拍照，我才能看到画面内容哦~"
    messages = _build_vlm_messages(question, image_base64, prev_image_base64)
    return _vlm_completion("LM Studio", messages, stream=False)


def openai_vlm_cam(question, image_base64=None, prev_image_base64=None):
    """（兼容包装）OpenAI 兼容 VLM"""
    if not image_base64:
        return "请上传图片或点击摄像头按钮拍照，我才能看到画面内容哦~"
    messages = _build_vlm_messages(question, image_base64, prev_image_base64)
    return _vlm_completion("OpenAI", messages, stream=False)


# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
def yolo_ocr_cam(question, image_base64=None, prev_image_base64=None):  # 本地YOLO-OCR-LLM摄像头画面识别理解
    """本地 YOLO+OCR 视觉分析。image_base64 为浏览器传入的 base64 图片数据。
    prev_image_base64 为前一张图，YOLO-OCR 暂不支持多图对比，忽略前一张。"""
    global cls_model, det_model, ocr
    if not image_base64:
        return "请上传图片或点击摄像头按钮拍照，我才能看到画面内容哦~"
    if cls_model is None or det_model is None or ocr is None:
        cls_model = YOLO('data/model/YOLO/yolo11s-cls.pt')
        det_model = YOLO('data/model/YOLO/yolo11s.pt')
        ocr = RapidOCR()

    # 将 base64 转为 cv2 图像
    base64_image = _strip_base64_prefix(image_base64)
    img_array = np.frombuffer(b64decode(base64_image), dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if frame is None:
        return "图片解析失败，请重新上传"

    cls_results = cls_model(frame)
    probs = cls_results[0].probs.data.cpu().numpy()
    names = cls_results[0].names
    top5_indices = probs.argsort()[-5:][::-1]
    scene_detection_result = []
    for cls_index in top5_indices:
        cls_name = names[cls_index]
        cls_conf = probs[cls_index]
        scene_detection_result.append(f"{cls_name},{cls_conf:.2f}")
    scene_detection_result = ";".join(scene_detection_result)
    det_results = det_model(frame)
    object_detection_result = []
    object_count = {}
    for det in det_results[0].boxes:
        det_name = det_results[0].names[int(det.cls)]
        if det_name in object_count:
            object_count[det_name] += 1
        else:
            object_count[det_name] = 1
    for obj_name, count in object_count.items():
        object_detection_result.append(f"{obj_name},{count}个")
    object_detection_result = ";".join(object_detection_result)
    ocr_results, _ = ocr(frame)
    text_detection_result = []
    try:
        for ocr_result in ocr_results:
            text_detection_result.append(ocr_result[1])
    except (TypeError, IndexError):
        print("OCR结果为空")
    text_detection_result = "\n".join(text_detection_result)
    if len(text_detection_result) > 0:
        text_detection_result = "文字检测结果:" + text_detection_result
    yolo_ocr_result = f"场景检测结果(场景名称,置信度):{scene_detection_result}\n物体检测结果(物体名称,数量):{object_detection_result}\n{text_detection_result}"
    ollama_client = OpenAI(base_url=ollama_url, api_key="ollama")
    messages = [{"role": "system",
                 "content": "你是一个专业的多模态大模型，请扮演一个有情感的人类和我对话，需要结合你看到的内容回答我的问题，仅需输出推测的场景行为。/no_think"},
                {"role": "user",
                 "content": f"\n{yolo_ocr_result}以上是你看到的内容，不要提及任何英文、置信度，不能拒绝回答我的问题。我的问题是:{question}"}]
    completion = ollama_client.chat.completions.create(model=ollama_llm_model, messages=messages)
    return completion.choices[0].message.content
