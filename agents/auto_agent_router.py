"""根据持久化开关状态，自动判断是否需要调用 Agent"""

from typing import Optional, Tuple


class AutoAgentRouter:
    """根据持久化开关状态，自动判断是否需要调用 Agent"""

    WEBSEARCH_KEYWORDS = [
        "搜索", "查", "查询", "查找", "搜", "搜一下", "找", "找一下",
        "有什么", "最新", "新闻", "资讯", "资料", "信息",
        "发生", "事件", "怎么样", "如何", "近况", "现状",
        "是谁", "是什么", "为什么", "多少", "多大", "多远",
    ]

    WEATHER_KEYWORDS = [
        "天气", "气温", "温度", "下雨", "下雪", "刮风", "雾霾",
        "预报", "晴", "阴", "多云",
    ]

    NEWS_KEYWORDS = [
        "新闻", "热点", "头条", "资讯", "时事", "报道",
    ]

    @classmethod
    def should_search(cls, msg: str) -> bool:
        """判断消息是否应该触发联网搜索"""
        return any(kw in msg for kw in cls.WEBSEARCH_KEYWORDS)

    @classmethod
    def should_weather(cls, msg: str) -> bool:
        """判断消息是否应该触发天气查询"""
        return any(kw in msg for kw in cls.WEATHER_KEYWORDS)

    @classmethod
    def should_news(cls, msg: str) -> bool:
        """判断消息是否应该触发新闻查询"""
        return any(kw in msg for kw in cls.NEWS_KEYWORDS)

    @classmethod
    def parse_slash_command(cls, msg: str) -> Optional[Tuple[str, dict]]:
        """解析斜杠命令，返回 (agent_id, params) 或 None"""
        msg = msg.strip()
        if not msg.startswith('/'):
            return None
        
        parts = msg[1:].split(' ', 1)
        cmd = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ''
        
        slash_map = {
            'search': ('search', {'query': rest}),
            'sousuo': ('search', {'query': rest}),
            'weather': ('weather', {'city': rest}),
            'tq': ('weather', {'city': rest}),
            'tianqi': ('weather', {'city': rest}),
            'news': ('news', {'category': rest}),
            'xinwen': ('news', {'category': rest}),
        }
        return slash_map.get(cmd)

    @classmethod
    def route(cls, msg: str, user_config: dict) -> Optional[Tuple[str, dict]]:
        """
        根据用户配置和消息内容，返回 (agent_id, params) 或 None
        """
        # 优先检查斜杠命令
        slash_result = cls.parse_slash_command(msg)
        if slash_result:
            agent_id, params = slash_result
            # 斜杠命令：用户显式输入，无条件执行
            return agent_id, params

        # 联网搜索开关
        if user_config.get("agent_websearch") == "on":
            if cls.should_search(msg):
                return "search", {"query": msg}

        # 天气开关
        if user_config.get("agent_weather") == "on":
            if cls.should_weather(msg):
                return "weather", {"city": ""}

        # 新闻开关
        if user_config.get("agent_news") == "on":
            if cls.should_news(msg):
                return "news", {"category": ""}

        return None
