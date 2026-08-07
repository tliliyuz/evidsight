"""版本恢复扫描 — Celery Beat 定时任务：卡死版本重投 + 卡死 KB 发布锁回滚

对齐 ADR-007 / RAG_PIPELINE.md §3.4（Worker 丢失恢复）：
- 非终态版本在 STUCK_VERSION_TIMEOUT（默认 300s）内未推进、且无活跃版本锁
  （即无 worker 正在处理）→ 重新投递 ingest_version，以 Version 状态机续跑。
- knowledge_bases.index_status 处于 updating/recovering 超过
  KB_LOCK_TIMEOUT（默认 600s）→ 发布锁疑似卡死，回滚为 ready。
  回滚安全的依据（ADR-007 原子发布顺序）：向量写入/active_version 切换均在
  MySQL 事务内完成；崩溃发生在提交前 DB 状态未变，发生在提交后旧版本向量
  残留但被版本作用域 id 隔离，两种情形下恢复 ready 均不产生错误检索结果。

Beat 调度由 celery_app.conf.beat_schedule 注册（celery_app.py），每 60s 执行。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.core.database import async_session
from app.ingest.celery_app import celery_app
from app.ingest.lock import (
    acquire_version_lock_async,
    release_version_lock_async,
)
from app.ingest.tasks import ingest_version
from app.ingest.versioning import PROCESSING_STAGES, QUEUED
from app.models.document_version import DocumentVersion
from app.models.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

_KB_LOCK_STATUSES = ("updating", "recovering")

# 恢复扫描覆盖的阶段：处理中阶段 + queued（对齐 RAG_PIPELINE.md §3.4：
# “queued 或超时非终态 Version 由周期扫描恢复”；Worker 在首个 Checkpoint
# 前崩溃、任务已被 ack 的场景会把版本留在 queued，必须同样可重投）。
SCAN_STATUSES = frozenset(PROCESSING_STAGES) | {QUEUED}


async def _scan_stuck_versions_async() -> dict:
    """扫描卡死版本与卡死 KB 发布锁并执行恢复，返回本次处理统计。"""
    now = datetime.now(timezone.utc)

    # 1. 卡死版本：非终态（含 queued）+ 超过超时阈值 + 无活跃锁 → 重投 ingest_version
    version_cutoff = now - timedelta(seconds=settings.STUCK_VERSION_TIMEOUT)
    async with async_session() as db:
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.status.in_(SCAN_STATUSES),
                DocumentVersion.updated_at < version_cutoff,
            )
        )
        stuck_versions = result.scalars().all()

    redispatch_ids: list[int] = []
    for v in stuck_versions:
        if await acquire_version_lock_async(v.uuid):
            # 无活跃锁 → 没有 worker 正在处理，安全重投（先释放锁再投递）
            await release_version_lock_async(v.uuid)
            redispatch_ids.append(v.id)
            logger.warning("恢复：版本 %s（id=%d）卡死超时，重新投递 ingest_version", v.uuid, v.id)

    for vid in redispatch_ids:
        ingest_version.delay(vid)

    # 2. 卡死 KB 发布锁：updating/recovering 超过阈值 → 回滚 ready
    kb_cutoff = now - timedelta(seconds=settings.KB_LOCK_TIMEOUT)
    async with async_session() as db:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.index_status.in_(_KB_LOCK_STATUSES),
                KnowledgeBase.updated_at < kb_cutoff,
            )
        )
        stuck_kbs = result.scalars().all()
        for kb in stuck_kbs:
            logger.warning("恢复：KB %d 发布锁（%s）卡死超时，回滚为 ready", kb.id, kb.index_status)
            kb.index_status = "ready"
        await db.commit()

    return {
        "stuck_versions": len(stuck_versions),
        "redispatched": len(redispatch_ids),
        "stuck_kbs": len(stuck_kbs),
    }


@celery_app.task(
    name="app.ingest.recovery_tasks.scan_stuck_versions",
    bind=True,
    max_retries=3,
    soft_time_limit=120,
)
def scan_stuck_versions(self) -> dict:
    """Celery Beat 周期任务：执行卡死版本/KB 恢复扫描。"""
    from app.ingest.tasks import _get_worker_loop

    return _get_worker_loop().run_until_complete(_scan_stuck_versions_async())
