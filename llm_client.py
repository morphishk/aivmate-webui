"""
LLM 客户端统一接口层

解决 zhipuai>=2.1.5 monkey-patch openai 模块导致的冲突。
所有 OpenAI 兼容引擎（OpenAI/Ollama/LM Studio）统一走此模块，
完全绕开 openai Python SDK，用 requests 直接调 HTTP API。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Iterator

import requests as rq

logger = logging.getLogger("llm_client")


# ── 异常类 ──────────────────────────────────────────────────

class LLMError(Exception):
    """LLM 调用基础异常"""
    pass


class APIAuthenticationError(LLMError):
    """401 - API key 无效或过期"""
    pass


class APIRateLimitError(LLMError):
    """429 - 请求过于频繁"""
    pass


class APIServerError(LLMError):
    """5xx - 服务端错误"""
    pass


# ── 兼容 openai SDK 的响应对象 ───────────────────────────────

class ChatMessage:
    """兼容 openai.ChatCompletionMessage"""
    def __init__(self, content: str, role: str = "assistant", **kwargs):
        self.content = content
        self.role = role
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChatChoice:
    """兼容 openai.ChatCompletion.Choice"""
    def __init__(self, message: ChatMessage, index: int = 0, finish_reason: str = "stop"):
        self.message = message
        self.index = index
        self.finish_reason = finish_reason


class ChatCompletion:
    """兼容 openai.ChatCompletion"""
    def __init__(self, choices: list[ChatChoice], id: str = "", model: str = "", **kwargs):
        self.choices = choices
        self.id = id
        self.model = model


# ── 兼容 openai SDK 的流式响应对象 ───────────────────────────

class Delta:
    """兼容 openai.types.chat.chat_completion_chunk.Delta"""
    def __init__(self, content: str | None = None, reasoning_content: str | None = None, role: str | None = None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.role = role


class ChoiceChunk:
    """兼容 openai.types.chat.chat_completion_chunk.Choice"""
    def __init__(self, delta: Delta, index: int = 0, finish_reason: str | None = None):
        self.delta = delta
        self.index = index
        self.finish_reason = finish_reason


class ChatCompletionChunk:
    """兼容 openai.types.chat.chat_completion_chunk.ChatCompletionChunk"""
    def __init__(self, choices: list[ChoiceChunk], id: str = "", model: str = ""):
        self.choices = choices
        self.id = id
        self.model = model


# ── 抽象基类 ─────────────────────────────────────────────────

class LLMClientBase(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    def chat_completions_create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        timeout: float = 120.0,
        **kwargs
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        """
        创建聊天完成

        Returns:
            stream=False: ChatCompletion 对象
            stream=True: Iterator[ChatCompletionChunk]，逐 chunk yield
        """
        pass

    @abstractmethod
    def models_list(self, timeout: float = 30.0) -> list[str]:
        """获取可用模型列表"""
        pass


# ── OpenAI 兼容客户端 ────────────────────────────────────────

class _CompletionsProxy:
    """兼容 openai SDK 的 client.chat.completions.create() 调用链"""
    def __init__(self, client: "OpenAICompatibleClient"):
        self._client = client

    def create(self, **kwargs):
        return self._client.chat_completions_create(**kwargs)


class _ChatProxy:
    """兼容 openai SDK 的 client.chat 属性"""
    def __init__(self, client: "OpenAICompatibleClient"):
        self.completions = _CompletionsProxy(client)


class OpenAICompatibleClient(LLMClientBase):
    """
    绕过 zhipuai monkey-patch，直接用 requests 调 OpenAI 兼容接口。
    支持同步调用、SSE 流式、模型列表获取。
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/') if base_url else ''
        self.api_key = api_key or ''
        self.session = rq.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        # 兼容 openai SDK 调用风格: client.chat.completions.create(...)
        self.chat = _ChatProxy(self)

    def _filter_payload(self, model: str, messages: list, **kwargs) -> dict:
        """过滤并构造请求体，仅保留服务端支持的参数"""
        payload = {"model": model, "messages": messages}
        supported = {
            "temperature", "max_tokens", "top_p", "frequency_penalty",
            "presence_penalty", "stop", "seed", "stream",
        }
        for k, v in kwargs.items():
            if k in supported:
                payload[k] = v
        return payload

    def _raise_for_status(self, resp: rq.Response):
        """统一错误处理"""
        if resp.status_code == 401:
            raise APIAuthenticationError("API key 无效或已过期")
        if resp.status_code == 429:
            raise APIRateLimitError("请求过于频繁，请稍后重试")
        if resp.status_code >= 500:
            raise APIServerError(f"服务器错误: {resp.status_code}")
        resp.raise_for_status()

    # ── 同步调用 ────────────────────────────────────────────

    def chat_completions_create(
        self, model: str, messages: list[dict],
        stream: bool = False, timeout: float = 120.0, **kwargs
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:

        url = f"{self.base_url}/chat/completions"
        payload = self._filter_payload(model, messages, **kwargs)
        payload["stream"] = stream

        if stream:
            return self._stream_chat(url, payload, timeout)

        resp = self.session.post(url, json=payload, timeout=timeout)
        self._raise_for_status(resp)
        data = resp.json()

        choices = [
            ChatChoice(
                message=ChatMessage(
                    content=c["message"]["content"],
                    role=c["message"].get("role", "assistant"),
                    reasoning_content=c["message"].get("reasoning_content"),
                ),
                index=c.get("index", 0),
                finish_reason=c.get("finish_reason", "stop"),
            )
            for c in data.get("choices", [])
        ]
        return ChatCompletion(choices=choices, id=data.get("id"), model=data.get("model"))

    # ── 流式调用 ────────────────────────────────────────────

    def _stream_chat(self, url: str, payload: dict, timeout: float) -> Iterator[ChatCompletionChunk]:
        """SSE 流式解析，逐 chunk yield 兼容 openai SDK 的对象"""
        resp = self.session.post(url, json=payload, timeout=timeout, stream=True)
        self._raise_for_status(resp)

        # 用字节级 iter_lines 避免 decode_unicode=True 跨 chunk 截断 UTF-8 字符
        for line_bytes in resp.iter_lines():
            if not line_bytes:
                continue
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice_data = choices[0]
                delta_data = choice_data.get("delta", {})
                delta = Delta(
                    content=delta_data.get("content"),
                    reasoning_content=delta_data.get("reasoning_content"),
                    role=delta_data.get("role"),
                )
                choice = ChoiceChunk(
                    delta=delta,
                    index=choice_data.get("index", 0),
                    finish_reason=choice_data.get("finish_reason"),
                )
                yield ChatCompletionChunk(
                    choices=[choice],
                    id=chunk.get("id", ""),
                    model=chunk.get("model", ""),
                )
            except (json.JSONDecodeError, KeyError, IndexError):
                logger.warning(f"SSE 解析异常: {data_str[:200]}")
                continue

    # ── 模型列表 ────────────────────────────────────────────

    def models_list(self, timeout: float = 30.0) -> list[str]:
        url = f"{self.base_url}/models"
        resp = self.session.get(url, timeout=timeout)
        self._raise_for_status(resp)
        data = resp.json()
        model_ids = [m["id"] for m in data.get("data", []) if "id" in m]
        model_ids.sort()
        return model_ids
