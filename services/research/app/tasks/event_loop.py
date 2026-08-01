"""Celery Worker 事件循环管理工具。

提供 Worker 进程内唯一持久事件循环，避免 `asyncio.run()` 反复创建/关闭 loop
导致 SQLAlchemy async engine / Redis async pool 绑定到已关闭 loop 的问题。
"""

import asyncio
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

_worker_loop: Optional[asyncio.AbstractEventLoop] = None

# Windows 下 aiomysql / redis.asyncio 需要 SelectorEventLoop，Proactor 会卡死或超时。
# 该策略必须在任何事件循环创建前设置。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def get_worker_loop() -> asyncio.AbstractEventLoop:
    """获取 Worker 进程内持久事件循环。

    - 首次调用创建并缓存 loop；后续直接复用。
    - 若缓存的 loop 被关闭，清理绑定到旧 loop 的全局 async 单例，然后新建 loop。
    - 供 Celery 任务使用 `loop.run_until_complete(...)` 执行异步逻辑，禁止再使用
      `asyncio.run(...)`。
    """
    global _worker_loop
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop is None or loop.is_closed():
        if loop is not None and loop.is_closed():
            _reset_async_resources()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Created persistent worker event loop: %s", loop)

    _worker_loop = loop
    return loop


def _reset_async_resources() -> None:
    """当检测到 loop 被意外关闭时，清理全局 async 单例。

    SQLAlchemy async engine 与 Redis async pool 内部的 Future/transport 会绑定到
    创建时的事件循环；loop 关闭后继续使用这些对象会触发
    "Future attached to a different loop" 或 "Event loop is closed"。
    通过 dispose/clear 强制它们在下次使用时重新初始化到新 loop。
    """
    try:
        from app.core.database import engine

        engine.dispose()
        logger.warning("Disposed SQLAlchemy async engine after loop closure")
    except Exception:
        logger.exception("Failed to dispose SQLAlchemy engine")

    try:
        import app.core.redis_client as _rc

        if getattr(_rc, "_async_client", None) is not None:
            _rc._async_client = None
        if getattr(_rc, "_async_pool", None) is not None:
            _rc._async_pool = None
        if getattr(_rc, "_threaded_client", None) is not None:
            _rc._threaded_client = None
        logger.warning("Cleared async Redis singletons after loop closure")
    except Exception:
        logger.exception("Failed to clear async Redis singletons")
