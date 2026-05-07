"""联网搜索 Agent"""

import logging

from agents.agent_base import BaseAgent, AgentContext, AgentResult
from agents.agent_registry import AgentRegistry
from function import ol_search

logger = logging.getLogger("agent")


@AgentRegistry.register
class SearchAgent(BaseAgent):
    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": "search",
            "name": "联网搜索",
            "icon": "🔍",
            "category": "info",
            "description": "联网搜索最新信息",
            "triggers": ["slash"],
            "slash_commands": ["/search", "/sousuo"],
            "order": 30,
            "params": [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "label": "搜索内容",
                    "placeholder": "请输入搜索关键词",
                }
            ],
        }

    @classmethod
    def execute(cls, params: dict, context: AgentContext) -> AgentResult:
        try:
            query = params.get("query", "")
            if not query:
                return AgentResult(
                    type="error",
                    title="搜索失败",
                    error="搜索内容不能为空",
                )

            result_text = ol_search(query)

            return AgentResult(
                type="text",
                title="🔍 搜索结果",
                data={"text": result_text},
            )
        except Exception as e:
            logger.error(f"SearchAgent 执行失败: {e}", exc_info=True)
            return AgentResult(
                type="error",
                title="搜索失败",
                error=f"搜索时发生错误: {str(e)}",
            )
