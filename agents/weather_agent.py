"""天气查询 Agent - 使用 Open-Meteo 免费天气API"""

import logging
import requests as rq

from agents.agent_base import BaseAgent, AgentContext, AgentResult
from agents.agent_registry import AgentRegistry

logger = logging.getLogger("agent")

# 常见城市经纬度映射（Open-Meteo 不需要 key，直接用经纬度查询）
CITY_COORDS = {
    "北京": (39.90, 116.40),
    "上海": (31.23, 121.47),
    "杭州": (30.27, 120.16),
    "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06),
    "成都": (30.57, 104.07),
    "武汉": (30.59, 114.31),
    "西安": (34.34, 108.94),
    "南京": (32.06, 118.78),
    "重庆": (29.56, 106.55),
    "天津": (39.13, 117.20),
    "苏州": (31.30, 120.58),
    "郑州": (34.75, 113.63),
    "长沙": (28.23, 112.98),
    "青岛": (36.07, 120.38),
    "宁波": (29.87, 121.55),
    "厦门": (24.48, 118.09),
    "大连": (38.92, 121.62),
    "沈阳": (41.80, 123.43),
    "济南": (36.65, 117.12),
}

# WMO Weather interpretation codes (WW)
WMO_CODES = {
    0: "☀️ 晴朗",
    1: "🌤️ 主要晴朗",
    2: "⛅ 部分多云",
    3: "☁️ 阴天",
    45: "🌫️ 雾",
    48: "🌫️ 雾凇",
    51: "🌦️ 毛毛雨（轻）",
    53: "🌦️ 毛毛雨（中）",
    55: "🌧️ 毛毛雨（密）",
    56: "🌧️ 冻雨（轻）",
    57: "🌧️ 冻雨（密）",
    61: "🌧️ 小雨",
    63: "🌧️ 中雨",
    65: "🌧️ 大雨",
    66: "🌨️ 冻雨（轻）",
    67: "🌨️ 冻雨（重）",
    71: "🌨️ 小雪",
    73: "🌨️ 中雪",
    75: "🌨️ 大雪",
    77: "🌨️ 雪粒",
    80: "🌦️ 阵雨（轻）",
    81: "🌦️ 阵雨（中）",
    82: "🌧️ 阵雨（强）",
    85: "🌨️ 阵雪（轻）",
    86: "🌨️ 阵雪（强）",
    95: "⛈️ 雷雨（轻/中）",
    96: "⛈️ 雷雨伴小冰雹",
    99: "⛈️ 雷雨伴大冰雹",
}


def _get_city_coords(city_name: str) -> tuple[float, float] | None:
    """根据城市名获取经纬度"""
    # 直接匹配
    if city_name in CITY_COORDS:
        return CITY_COORDS[city_name]
    # 去掉"市"后缀匹配
    if city_name.endswith("市"):
        name = city_name[:-1]
        if name in CITY_COORDS:
            return CITY_COORDS[name]
    # 模糊匹配（城市名包含）
    for cn, coords in CITY_COORDS.items():
        if cn in city_name or city_name in cn:
            return coords
    return None


def _fetch_weather(lat: float, lon: float) -> dict:
    """调用 Open-Meteo API 获取天气"""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
        f"&timezone=Asia/Shanghai"
    )
    res = rq.get(url, timeout=10)
    res.raise_for_status()
    return res.json()


@AgentRegistry.register
class WeatherAgent(BaseAgent):
    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": "weather",
            "name": "天气查询",
            "icon": "🌤️",
            "category": "info",
            "description": "查询指定城市的实时天气",
            "triggers": ["toolbar", "slash"],
            "slash_commands": ["/weather", "/tq", "/tianqi"],
            "order": 10,
            "params": [
                {
                    "name": "city",
                    "type": "string",
                    "required": False,
                    "label": "城市",
                    "placeholder": "请输入城市，如：杭州",
                    "default_from_config": "weather_city",
                }
            ],
        }

    @classmethod
    def execute(cls, params: dict, context: AgentContext) -> AgentResult:
        try:
            city = params.get("city") or context.user_config.get("weather_city", "杭州")
            coords = _get_city_coords(city)
            if not coords:
                # fallback：尝试用配置中的默认城市
                fallback_city = context.user_config.get("weather_city", "杭州")
                if fallback_city and fallback_city != city:
                    coords = _get_city_coords(fallback_city)
                    if coords:
                        city = fallback_city
            if not coords:
                return AgentResult(
                    type="error",
                    title="天气查询失败",
                    error=f"暂不支持查询城市「{city}」的天气。支持的城市：{', '.join(CITY_COORDS.keys())}",
                )

            lat, lon = coords
            data = _fetch_weather(lat, lon)
            current = data.get("current", {})
            temp = current.get("temperature_2m", "-")
            humidity = current.get("relative_humidity_2m", "-")
            code = current.get("weather_code", -1)
            weather_desc = WMO_CODES.get(code, "🌡️ 未知天气")

            detail = f"{weather_desc}，气温 {temp}°C，相对湿度 {humidity}%"

            return AgentResult(
                type="card",
                title=f"🌤️ {city} 天气",
                data={
                    "city": city,
                    "summary": weather_desc,
                    "detail": detail,
                    "source": "Open-Meteo 气象数据",
                },
            )
        except Exception as e:
            logger.error(f"WeatherAgent 执行失败: {e}", exc_info=True)
            return AgentResult(
                type="error",
                title="天气查询失败",
                error=f"查询天气时发生错误: {str(e)}",
            )
