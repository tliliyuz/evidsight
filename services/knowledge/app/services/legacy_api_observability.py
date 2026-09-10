"""旧 API 调用量观测。"""

import logging

from app.core.redis_client import get_async_redis

logger = logging.getLogger(__name__)


async def record_old_chat_call(route: str) -> None:
    """按路由累计 namespaced 废弃调用量；观测失败不阻断业务。"""
    try:
        redis = await get_async_redis()
        await redis.incr(f"docmind:metrics:legacy_chat_api_calls:{route}")
    except Exception:
        logger.warning("旧 Chat API 调用量记录失败: route=%s", route, exc_info=True)
