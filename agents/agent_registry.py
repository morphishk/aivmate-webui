"""Agent 注册中心，单例模式，支持装饰器注册与自动发现"""

from typing import Type, Optional
from agents.agent_base import BaseAgent


class AgentRegistry:
    """Agent 注册中心，单例模式"""

    _instance = None
    _agents: dict[str, Type[BaseAgent]] = {}
    _discovered = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
        """装饰器注册方式"""
        meta = agent_class.metadata()
        agent_id = meta["id"]
        cls._agents[agent_id] = agent_class
        return agent_class

    @classmethod
    def get(cls, agent_id: str) -> Optional[Type[BaseAgent]]:
        """根据 ID 获取 Agent 类"""
        return cls._agents.get(agent_id)

    @classmethod
    def list_all(cls) -> list[dict]:
        """返回所有 Agent 元数据列表，供 /api/agents 使用"""
        agents = [agent.metadata() for agent in cls._agents.values()]
        agents.sort(key=lambda x: x.get("order", 100))
        return agents

    @classmethod
    def discover_and_register(cls):
        """自动发现 agents/ 目录下的所有 Agent 并注册"""
        if cls._discovered:
            return
        import os
        import importlib

        agents_dir = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(agents_dir):
            if filename.endswith("_agent.py"):
                module_name = f"agents.{filename[:-3]}"
                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    import logging
                    logging.getLogger("agent").warning(
                        f"自动发现 Agent 模块失败: {module_name}, 错误: {e}"
                    )
        cls._discovered = True

    @classmethod
    def reset(cls):
        """重置注册状态（主要用于测试）"""
        cls._agents.clear()
        cls._discovered = False
