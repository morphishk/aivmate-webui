"""新闻查询 Agent - 使用百度热搜API"""

import logging
import time
import requests as rq

from agents.agent_base import BaseAgent, AgentContext, AgentResult
from agents.agent_registry import AgentRegistry

logger = logging.getLogger("agent")


def _fetch_baidu_hot() -> list[dict]:
    """调用百度热搜API获取热搜列表（带1次重试）"""
    url = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://top.baidu.com/",
    }
    last_err = None
    for attempt in range(2):
        try:
            res = rq.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()

            items = []
            cards = data.get("data", {}).get("cards", [])
            if cards:
                contents = cards[0].get("content", [])
                if contents:
                    for item in contents[0].get("content", [])[:10]:
                        word = item.get("word", "")
                        if word:
                            items.append({"title": word})
            return items
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(1)
    logger.warning(f"百度热搜获取失败（已重试1次）: {last_err}")
    return []


@AgentRegistry.register
class NewsAgent(BaseAgent):
    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": "news",
            "name": "新闻查询",
            "icon": "📰",
            "category": "info",
            "description": "查询今日热点新闻",
            "triggers": ["toolbar", "slash"],
            "slash_commands": ["/news", "/xinwen"],
            "order": 20,
            "params": [],
        }

    @classmethod
    def execute(cls, params: dict, context: AgentContext) -> AgentResult:
        try:
            items = _fetch_baidu_hot()
            if not items:
                return AgentResult(
                    type="error",
                    title="新闻查询失败",
                    error="暂时无法获取热点新闻，请稍后再试",
                )

            return AgentResult(
                type="list",
                title="📰 今日热点",
                data={"items": items},
            )
        except Exception as e:
            logger.error(f"NewsAgent 执行失败: {e}", exc_info=True)
            return AgentResult(
                type="error",
                title="新闻查询失败",
                error=f"查询新闻时发生错误: {str(e)}",
            )
