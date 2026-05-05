"""
ZhipuAI 客户端兼容封装
原项目使用 from zai import ZhipuAiClient
这里提供对 zhipuai.ZhipuAI 的兼容包装
"""
try:
    from zhipuai import ZhipuAI as ZhipuAiClient
except ImportError:
    # 如果 zhipuai 未安装，提供一个占位类，避免导入崩溃
    class ZhipuAiClient:
        def __init__(self, api_key=None):
            raise ImportError(
                "zhipuai SDK 未安装。请执行: pip install zhipuai"
            )

__all__ = ["ZhipuAiClient"]
