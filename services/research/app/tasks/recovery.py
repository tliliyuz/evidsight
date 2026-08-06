"""Worker 崩溃恢复逻辑 —— 按数据库租约扫描。

提供启动恢复和 Worker 就绪恢复两种入口：
- 启动恢复：FastAPI lifespan 启动时调用
- Worker 就绪恢复：Celery Worker 启动完成时调用

恢复语义对齐 RESEARCH_PIPELINE §13.5 / DATABASE.md §8 / ADR-008：
1. Scanner 按 (status='running', lease_expires_at) 查找租约过期或为空的运行任务；
2. 锁定后再次确认租约过期（条件更新领取，防止与新 Worker 竞争）；
3. 将遗留 running Step 置为 retrying（或按重试上限 failed）；
4. 清除旧 owner、递增恢复计数并重新投递到 research.execute（与 API 创建共用执行队列）；
5. 启动扫描、周期扫描和手动恢复必须调用同一恢复服务。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import or_ as sa_or, select as sa_select, update as sa_update

from app.config import settings
from app.core.database import async_session_factory
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.tasks.lock import check_task_lock_async

logger = logging.getLogger(__name__)


async def recover_stale_tasks(check_lock: bool = True) -> list[str]:
    """扫描并按租约过期恢复过时 running 任务。

    Args:
        check_lock: 是否检查任务级锁。True 时只有锁不存在才恢复；
                    False 时仅按租约过期恢复（用于启动恢复兜底）。

    Returns:
        重新投递的任务 ID 列表
    """
    recovered: list[str] = []
    if not settings.STARTUP_RECOVERY_ENABLED:
        return recovered

    now = datetime.now(timezone.utc)
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                sa_select(ResearchTask.id)
                .where(
                    ResearchTask.status == "running",
                    sa_or(
                        ResearchTask.lease_expires_at.is_(None),
                        ResearchTask.lease_expires_at < now,
                    ),
                )
                .order_by(ResearchTask.started_at)
            )
            candidate_ids = [row[0] for row in result.all()]
    except Exception:
        logger.exception("扫描租约过期的 running 任务失败")
        return recovered

    if not candidate_ids:
        logger.info("未发现租约过期的 running 任务")
        return recovered

    # 局部导入避免循环依赖
    from app.tasks.research_task import execute_research_task

    for task_id in candidate_ids:
        task_id = str(task_id)
        try:
            if check_lock:
                lock_exists = await check_task_lock_async(task_id)
                if lock_exists:
                    logger.info(
                        "任务级锁仍存在，跳过恢复（可能仍有 Worker 执行）: task_id=%s",
                        task_id,
                    )
                    continue

            async with async_session_factory() as session:
                # 锁定并再次确认租约过期：条件更新领取（只有仍过期/为空才成功），
                # 防止与已恢复的新 Worker 竞争。
                claimed = await _claim_expired_lease(session, task_id, "recovery-scanner")
                if not claimed:
                    logger.info(
                        "恢复扫描领取租约失败（租约已被新 Worker 领取）: task_id=%s",
                        task_id,
                    )
                    continue

                # 遗留 running Step → retrying（或按重试上限 failed）
                await _mark_stale_running_steps(session, task_id)

                # 清除旧 owner，递增恢复计数（DATABASE.md §8）
                await _clear_owner_and_increment_recovery(session, task_id)

                await session.commit()

            execute_research_task.delay(task_id)
            recovered.append(task_id)
            logger.warning(
                "已重新投递租约过期的任务: task_id=%s, recovery_count 已递增",
                task_id,
            )
        except Exception:
            logger.exception("重新投递租约过期任务失败: task_id=%s", task_id)

    return recovered


async def _claim_expired_lease(session, task_id: str, worker_id: str) -> bool:
    """条件领取租约，用于再次确认租约确实过期（与 §13.1 同一领取语义）。"""
    now = datetime.now(timezone.utc)

    result = await session.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status == "running",
            ResearchTask.cancel_requested_at.is_(None),
            sa_or(
                ResearchTask.lease_expires_at.is_(None),
                ResearchTask.lease_expires_at < now,
            ),
        )
        .values(
            lease_owner=worker_id,
            lease_expires_at=now,
            lease_generation=ResearchTask.lease_generation + 1,
        )
    )
    return result.rowcount > 0


async def _mark_stale_running_steps(session, task_id: str) -> None:
    """遗留 running Step 置为 retrying；超过重试上限的置为 failed。"""
    result = await session.execute(
        sa_update(ResearchStep)
        .where(
            ResearchStep.task_id == task_id,
            ResearchStep.status == "running",
        )
        .values(
            status="retrying",
            error_code=None,
            error_message=None,
        )
    )
    if result.rowcount > 0:
        logger.info(
            "恢复扫描将遗留 running Step 置为 retrying: task_id=%s, count=%d",
            task_id, result.rowcount,
        )


async def _clear_owner_and_increment_recovery(session, task_id: str) -> None:
    """清除旧 owner、递增恢复计数（DATABASE.md §8 第 3 步）。"""
    result = await session.execute(
        sa_update(ResearchTask)
        .where(ResearchTask.id == task_id)
        .values(
            lease_owner=None,
            lease_expires_at=None,
            recovery_count=ResearchTask.recovery_count + 1,
        )
    )
    if result.rowcount > 0:
        logger.info(
            "恢复扫描清除旧 owner 并递增恢复计数: task_id=%s",
            task_id,
        )
