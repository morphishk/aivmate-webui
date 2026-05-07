"""Agent 抽象基类与标准数据结构"""

from abc import ABC, abstractmethod
from typing import Any


class AgentContext:
    """Agent 执行上下文"""

    def __init__(self, session_id: str, user_config: dict, history: list[dict]):
        self.session_id = session_id
        self.user_config = user_config
        self.history = history


class AgentResult:
    """Agent 执行结果标准结构"""

    def __init__(
        self,
        type: str,
        data: Any = None,
        title: str = "",
        error: str = "",
    ):
        self.type = type       # "text" | "card" | "list" | "html" | "error"
        self.data = data       # 类型相关的结构化数据
        self.title = title     # 结果标题（用于消息展示）
        self.error = error     # 错误信息（如有）

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "title": self.title,
            "error": self.error,
        }


class BaseAgent(ABC):
    """所有 Agent 必须继承的抽象基类"""

    @classmethod
    @abstractmethod
    def metadata(cls) -> dict:
        """
        返回 Agent 元数据，用于 /api/agents 接口和前端展示。
        """
        pass

    @classmethod
    @abstractmethod
    def execute(cls, params: dict, context: AgentContext) -> AgentResult:
        """
        执行 Agent 逻辑。
        params: 前端传入的参数（已校验必填项）
        context: 执行上下文（会话ID、用户配置、历史消息）
        return: AgentResult 标准结果
        """
        pass

    @classmethod
    def validate_params(cls, params: dict) -> tuple[bool, str]:
        """参数校验，默认实现检查必填项。子类可重写。"""
        meta = cls.metadata()
        for p in meta.get("params", []):
            if p.get("required") and not params.get(p["name"]):
                return False, f"参数 {p['label']} 不能为空"
        return True, ""
