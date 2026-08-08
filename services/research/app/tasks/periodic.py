"""
Celery Beat 定时任务 —— 数据 TTL 清理 + 周期恢复扫描。

任务：
- cleanup_old_research_tasks: 删除已完成超过 N 天的研究任务（DB 级联删除子表 + Redis 孤儿锁清理）
- recover_expired_research_tasks: 周期 Recovery Scanner（RESEARCH_PIPELINE §13.5/§13.6，
  纯 DB lease 恢复过期 running 任务 + pending 重投递）

调度入口：app/tasks/celery_app.py 的 beat_schedule。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select

from app.config import settings
from app.core.database import async_session_factory
from app.core.redis_client import get_redis
from app.models.research_task import ResearchTask
from app.tasks.celery_app import celery_app
from app.tasks.event_loop import get_worker_loop
from app.tasks.lock import KEY_PREFIX, TASK_LOCK_PREFIX

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.periodic.recover_expired_research_tasks",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def recover_expired_research_tasks(self) -> dict:
    """周期 Recovery Scanner：恢复租约过期的 running 任务并重投递长时间 pending 任务。

    与 API 启动、Worker 就绪、手动治理调用同一恢复服务
    （app.tasks.recovery.recover_stale_tasks，纯 DB lease，不依赖 Redis）。
    投递失败的任务保持可再次被扫描发现，不留 scanner owner 占用。
    """
    from app.tasks.event_loop import get_worker_loop
    from app.tasks.recovery import recover_stale_tasks

    try:
        recovered = get_worker_loop().run_until_complete(recover_stale_tasks())
    except Exception as exc:
        logger.exception("[recovery] 周期恢复扫描失败")
        raise self.retry(exc=exc, countdown=60) from exc

    if recovered:
        logger.warning(
            "[recovery] 周期扫描：已恢复/重投递 %d 个任务: %s", len(recovered), recovered
        )
    else:
        logger.info("[recovery] 周期扫描完成：无待恢复任务")
    return {"recovered_tasks": len(recovered)}


@celery_app.task(name="app.tasks.periodic.cleanup_old_research_tasks", bind=True, max_retries=3)
def cleanup_old_research_tasks(self, max_age_days: int | None = None) -> dict:
    """清理已完成超过 max_age_days 天的研究任务。

    数据库层面通过 ON DELETE CASCADE 自动清理关联子表；
    任务完成后顺带扫描并删除对应任务 ID 的 Redis 孤儿锁 Key。

    Args:
        max_age_days: 任务保留天数，默认读取 CLEANUP_TASK_MAX_AGE_DAYS 或 30

    Returns:
        {"deleted_tasks": int, "orphan_lock_keys_removed": int}
    """
    if max_age_days is None:
        max_age_days = getattr(settings, "CLEANUP_TASK_MAX_AGE_DAYS", 30)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    logger.info("[cleanup] 开始清理 completed_at < %s 的研究任务", cutoff.isoformat())

    deleted_count = 0
    try:
        deleted_count = get_worker_loop().run_until_complete(_delete_old_tasks(cutoff))
    except Exception as exc:
        logger.exception("[cleanup] 清理旧研究任务失败")
        raise self.retry(exc=exc, countdown=60) from exc

    # 清理孤儿 Redis 锁（幂等锁 + 任务级锁）
    orphan_removed = _cleanup_orphan_task_locks()

    logger.info(
        "[cleanup] 完成：删除研究任务 %d 条，清理 Redis 孤儿锁 %d 个",
        deleted_count,
        orphan_removed,
    )
    return {"deleted_tasks": deleted_count, "orphan_lock_keys_removed": orphan_removed}


async def _delete_old_tasks(cutoff: datetime) -> int:
    """异步执行 DB 删除，返回删除行数。"""
    async with async_session_factory() as session:
        result = await session.execute(
            sa_delete(ResearchTask).where(
                ResearchTask.completed_at.isnot(None),
                ResearchTask.completed_at < cutoff,
            )
        )
        await session.commit()
        return result.rowcount


def _cleanup_orphan_task_locks() -> int:
    """扫描 Redis 中任务相关锁，删除对应任务已不存在的孤儿 Key。

    仅处理任务级锁（rm:task_lock:{task_id}）和 Step 幂等锁（rm:idempotency:{task_id}:*），
    通过异步 DB 批量存在性检查避免 N+1 查询。
    """
    redis_client = get_redis()
    removed = 0

    try:
        # 收集所有可能的任务 ID
        task_ids_from_locks: set[str] = set()
        lock_keys: list[str] = []

        for pattern in [f"{TASK_LOCK_PREFIX}:*", f"{KEY_PREFIX}:*"]:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    task_id = _extract_task_id_from_lock_key(key_str)
                    if task_id:
                        task_ids_from_locks.add(task_id)
                        lock_keys.append(key_str)
                if cursor == 0:
                    break

        if not task_ids_from_locks:
            return 0

        # 批量检查 DB 存在性
        existing_task_ids = _check_tasks_exist(task_ids_from_locks)

        # 删除不存在任务的锁
        for key in lock_keys:
            task_id = _extract_task_id_from_lock_key(key)
            if task_id and task_id not in existing_task_ids:
                redis_client.delete(key)
                removed += 1
                logger.debug("[cleanup] 删除孤儿锁: %s", key)

    except Exception:
        logger.exception("[cleanup] 清理 Redis 孤儿锁失败，继续执行")
        # 锁清理是兜底，不阻塞主流程

    return removed


def _extract_task_id_from_lock_key(key: str) -> str | None:
    """从 Redis 锁 Key 中提取任务 ID。

    支持格式：
    - rm:task_lock:{task_id}
    - rm:idempotency:{task_id}:{step_type}
    """
    parts = key.split(":")
    if len(parts) >= 3 and parts[0] == "rm":
        if parts[1] == "task_lock" and len(parts) == 3:
            return parts[2]
        if parts[1] == "idempotency" and len(parts) >= 3:
            return parts[2]
    return None


def _check_tasks_exist(task_ids: set[str]) -> set[str]:
    """异步批量检查任务是否存在，返回存在的任务 ID 集合。"""
    return get_worker_loop().run_until_complete(_check_tasks_exist_async(task_ids))


async def _check_tasks_exist_async(task_ids: set[str]) -> set[str]:
    """异步批量检查任务是否存在。"""
    if not task_ids:
        return set()

    async with async_session_factory() as session:
        result = await session.execute(
            sa_select(ResearchTask.id).where(ResearchTask.id.in_(task_ids))
        )
        return {row[0] for row in result.all()}
