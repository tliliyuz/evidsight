"""Worker 崩溃恢复与 pending 重投递 —— 按数据库租约扫描（纯 DB，无 Redis）。

提供三种统一入口（RESEARCH_PIPELINE §13.5）：
- API 启动恢复：FastAPI lifespan 启动时调用；
- Worker 就绪恢复：Celery Worker 启动完成时调用；
- 周期扫描：Celery Beat 周期调用（`RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS`）。

恢复语义对齐 RESEARCH_PIPELINE §13.5/§13.6、DATABASE.md §8、ADR-008：
1. Scanner 按 `(status='running', lease_expires_at 为空或已过期)` 查找过期运行任务；
2. 条件领取 scanner generation 再次确认租约过期（防止与新 Worker 竞争）；
3. 将遗留 running Step 置为 retrying（或按重试上限 failed）；
4. 递增恢复计数并保留 scanner handoff 租约，重新投递到 `research.execute`
   （与 API 创建共用执行队列，不使用独立 recovery 队列）；
   handoff 租约使下一轮扫描条件不命中 → 只恢复一次（评审 🔴2）；
   投递失败时清除 handoff 租约，下轮可再发现；
5. pending 任务超过阈值且无有效租约 → 递增 `redelivery_count` 并重投；
   超过最大重投次数 → 创建受控失败事实（`planning` failed Step E3118），
   由 `TaskStateResolver` 推导 `failed` 终态，扫描器不直接写终态；
6. 启动扫描、周期扫描和手动恢复必须调用同一恢复服务。

终态纪律：Scanner 不直接写终态；重投递失败时任务保持可再次被扫描发现，
不留永久被 scanner owner 占用的租约。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_ as sa_or
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update

from app.config import settings
from app.core.database import async_session_factory
from app.core.task_state_resolver import TaskStateResolver
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.services.task_lifecycle import RECOVERY_SCANNER_WORKER_ID

logger = logging.getLogger(__name__)


async def recover_stale_tasks() -> list[str]:
    """扫描并恢复过时 running 任务 + 重投递长时间 pending 任务（纯 DB lease）。

    Returns:
        重新投递的任务 ID 列表
    """
    recovered: list[str] = []
    if not settings.STARTUP_RECOVERY_ENABLED:
        return recovered

    now = datetime.now(timezone.utc)
    try:
        async with async_session_factory() as session:
            # 1. 租约过期 / 为空的 running 任务
            running_result = await session.execute(
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
            candidate_ids = [str(row[0]) for row in running_result.all()]

            # 2. 超过阈值仍 pending、无有效租约的任务（§13.6）
            pending_threshold = now - timedelta(
                seconds=settings.PENDING_REDELIVERY_THRESHOLD_SECONDS
            )
            pending_result = await session.execute(
                sa_select(ResearchTask.id).where(
                    ResearchTask.status == "pending",
                    ResearchTask.started_at.is_not(None),
                    ResearchTask.started_at < pending_threshold,
                    sa_or(
                        ResearchTask.lease_expires_at.is_(None),
                        ResearchTask.lease_expires_at < now,
                    ),
                )
            )
            stale_pending_ids = [str(row[0]) for row in pending_result.all()]
    except Exception:
        logger.exception("扫描租约过期 / pending 任务失败")
        return recovered

    if not candidate_ids and not stale_pending_ids:
        logger.info("未发现租约过期或需重投递的任务")
        return recovered

    # 局部导入避免循环依赖
    from app.tasks.research_task import execute_research_task

    for task_id in candidate_ids:
        try:
            async with async_session_factory() as session:
                # 条件领取 scanner generation：只有仍过期/为空才成功，防止与已恢复的新 Worker 竞争
                claimed = await _claim_expired_lease(session, task_id, RECOVERY_SCANNER_WORKER_ID)
                if not claimed:
                    logger.info(
                        "恢复扫描领取租约失败（租约已被新 Worker 领取）: task_id=%s",
                        task_id,
                    )
                    continue

                # 遗留 running Step → retrying（或按重试上限 failed）
                await _mark_stale_running_steps(session, task_id)

                # 递增恢复计数，保留 scanner handoff 租约（§13.5，评审 🔴2）：
                # 下一轮扫描条件（租约为空/已过期）不命中 → 只恢复一次；
                # 新 Worker 领取条件接受 scanner handoff 并立即接手。
                await _increment_recovery(session, task_id)

                await session.commit()
        except Exception:
            logger.exception("重新投递租约过期任务失败: task_id=%s", task_id)
            continue

        try:
            execute_research_task.delay(task_id)
        except Exception:
            # 投递失败：清除 scanner handoff 租约，保证下轮可再被发现（§13.5）
            async with async_session_factory() as session:
                await _clear_recovery_lease(session, task_id)
                await session.commit()
            logger.exception("恢复投递失败，已清除 scanner 租约待下轮重扫: task_id=%s", task_id)
            continue

        recovered.append(task_id)
        logger.warning(
            "已重新投递租约过期的任务: task_id=%s, recovery_count 已递增",
            task_id,
        )

    for task_id in stale_pending_ids:
        try:
            outcome = await _handle_stale_pending(task_id)
            if outcome == "redispatched":
                execute_research_task.delay(task_id)
                recovered.append(task_id)
                logger.warning(
                    "pending 任务已重投: task_id=%s, redelivery_count 已递增",
                    task_id,
                )
            elif outcome == "failed":
                logger.warning(
                    "pending 任务重投超过上限，已创建受控失败事实并由 Resolver 推导终态: "
                    "task_id=%s",
                    task_id,
                )
        except Exception:
            logger.exception("pending 重投递处理失败: task_id=%s", task_id)

    return recovered


async def _handle_stale_pending(task_id: str) -> str:
    """处理超过阈值仍 pending 且无有效租约的任务（RESEARCH_PIPELINE §13.6）。

    - `redelivery_count` < 上限：条件递增计数并重投；
    - 达到上限：创建受控失败事实（planning failed Step E3118），
      由 TaskStateResolver 推导 `failed` 终态。

    Returns:
        "redispatched" / "failed" / "skipped"
    """
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None or task.status != "pending":
            return "skipped"
        # 并发 Worker 可能已领取：有有效租约则跳过
        if task.lease_expires_at is not None and task.lease_expires_at >= now:
            return "skipped"

        if task.redelivery_count < settings.PENDING_REDELIVERY_MAX_RETRIES:
            # 条件递增：仅仍 pending 且无有效租约时生效（幂等）
            result = await session.execute(
                sa_update(ResearchTask)
                .where(
                    ResearchTask.id == task_id,
                    ResearchTask.status == "pending",
                    sa_or(
                        ResearchTask.lease_expires_at.is_(None),
                        ResearchTask.lease_expires_at < datetime.now(timezone.utc),
                    ),
                )
                .values(redelivery_count=ResearchTask.redelivery_count + 1)
            )
            await session.commit()
            return "redispatched" if result.rowcount > 0 else "skipped"

        # 超过最大重投次数：受控失败事实 → Resolver 推导终态（扫描器不直接写终态）
        await _create_pending_failure_fact(session, task)
        await session.commit()
        return "failed"


async def _create_pending_failure_fact(session, task: ResearchTask) -> None:
    """创建 planning failed Step（E3118）作为受控失败事实，并由 Resolver 推导终态。

    E3118 在 `TaskStateResolver.FATAL_STEP_ERROR_CODES` 中，因此 Resolver
    依据该 Step 事实推导 `failed`。扫描器只创建事实并执行 Resolver 的推导结果，
    不自行写死终态（RESEARCH_PIPELINE §13.5/§13.6）。
    """
    now = datetime.now(timezone.utc)
    failure_step = ResearchStep(
        task_id=task.id,
        step_type="planning",
        status="failed",
        error_code="E3118",
        error_message="任务长时间未被 Worker 拾取，pending 重投递超过上限，已判定失败",
        started_at=now,
        completed_at=now,
    )
    session.add(failure_step)
    await session.flush()

    resolver = TaskStateResolver()
    new_status, error_info = resolver.resolve(
        task,
        steps=[failure_step],
        evidence_count=0,
        published_completeness=None,
    )

    values: dict = {
        "status": new_status,
        "completed_at": datetime.now(timezone.utc),
    }
    if error_info:
        values["error_code"] = error_info.get("error_code")
        values["error_message"] = error_info.get("error_message")
        values["recoverable"] = error_info.get("recoverable", False)

    await session.execute(
        sa_update(ResearchTask)
        .where(ResearchTask.id == task.id, ResearchTask.status == "pending")
        .values(**values)
    )
    logger.warning(
        "pending 重投递超限，受控失败事实已创建并由 Resolver 推导: task_id=%s, status=%s",
        task.id,
        new_status,
    )


async def _claim_expired_lease(session, task_id: str, worker_id: str) -> bool:
    """条件领取租约，用于再次确认租约确实过期（与 §13.1 同一领取语义）。

    `lease_expires_at` 推到未来（租约时长），使并发 Scanner 的 WHERE
    （租约已过期）不命中，保证「两个 Scanner 并发只恢复一次」；
    提交后保留 scanner handoff 租约（评审 🔴2），新 Worker 领取后接手，
    下轮扫描不再命中；投递失败由 `_clear_recovery_lease` 清除。
    """
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
            lease_expires_at=now + timedelta(seconds=settings.RESEARCH_TASK_LEASE_TTL_SECONDS),
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
            task_id,
            result.rowcount,
        )


async def _increment_recovery(session, task_id: str) -> None:
    """递增恢复计数，保留 scanner handoff 租约（DATABASE.md §8 / §13.5，评审 🔴2）。

    不清除 owner/expiry：Scanner 恢复成功后保留 handoff 租约，下一轮扫描
    （租约为空或已过期）不命中，保证「只恢复一次」；新 Worker 领取条件接受
    scanner handoff 并立即接手。投递失败时由 `_clear_recovery_lease` 清除。
    """
    result = await session.execute(
        sa_update(ResearchTask)
        .where(ResearchTask.id == task_id)
        .values(recovery_count=ResearchTask.recovery_count + 1)
    )
    if result.rowcount > 0:
        logger.info(
            "恢复扫描递增恢复计数并保留 scanner handoff 租约: task_id=%s",
            task_id,
        )


async def _clear_recovery_lease(session, task_id: str) -> None:
    """投递失败时清除 scanner handoff 租约，使任务下轮可再被发现（§13.5）。

    仅当 owner 仍是 scanner 时清除，避免误清已接手 Worker 的租约。
    """
    result = await session.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.lease_owner == RECOVERY_SCANNER_WORKER_ID,
        )
        .values(lease_owner=None, lease_expires_at=None)
    )
    if result.rowcount > 0:
        logger.warning(
            "已清除 scanner handoff 租约（投递失败，下轮重扫）: task_id=%s",
            task_id,
        )
