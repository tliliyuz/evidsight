"""任务生命周期共享原语 —— 锁、CAS 状态转换、紧急失败、租约协议。

本模块抽取 PipelineOrchestrator 与 AgentRuntime 共用的低风险原语，
旧编排器内部方法保持不动，避免测试漂移。

租约协议对齐 RESEARCH_PIPELINE §13.1 / DATABASE.md §8 / ADR-008：
- Worker 领取与续租使用条件更新（WHERE 匹配当前 owner 与 generation）；
- Step 提交必须与 Task 的 owner、generation 同事务校验；
- 失去租约的 Worker 立即停止，不提交业务结果。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_ as sa_or
from sqlalchemy import select as sa_select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.metrics import emit_task_status_transition
from app.models.enums import STEP_TYPE_ENUM
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_TASK_CREATED,
    SSEBridge,
)
from app.tasks.lock import (
    acquire_task_lock_async,
    refresh_task_lock_async,
    release_task_lock_async,
)

logger = logging.getLogger(__name__)

PHASE_ORDER: list[str] = list(STEP_TYPE_ENUM)


async def claim_task_lease(
    session: AsyncSession,
    task_id: str,
    worker_id: str,
    ttl_seconds: int | None = None,
) -> int | None:
    """Worker 条件领取 Task 租约。

    单条条件更新（DATABASE.md §8）：Task 非终态、未请求取消、租约为空或已过期
    时，写入 lease_owner / lease_expires_at 并递增 lease_generation。

    Args:
        session: 异步 DB 会话
        task_id: 任务 UUID
        worker_id: Worker 标识（当前执行进程）
        ttl_seconds: 租约时长（秒），默认读取配置

    Returns:
        新 lease_generation；领取失败返回 None。
    """
    if ttl_seconds is None:
        ttl_seconds = settings.RESEARCH_TASK_LEASE_TTL_SECONDS
    now = datetime.now(timezone.utc)
    result = await session.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status.in_(["pending", "running"]),
            ResearchTask.cancel_requested_at.is_(None),
            sa_or(
                ResearchTask.lease_expires_at.is_(None),
                ResearchTask.lease_expires_at < now,
            ),
        )
        .values(
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=ttl_seconds),
            lease_generation=ResearchTask.lease_generation + 1,
        )
    )
    if result.rowcount == 0:
        logger.warning("租约领取失败（条件不满足）: task_id=%s, worker=%s", task_id, worker_id)
        return None

    # 读取递增后的 generation
    row = await session.execute(
        sa_select(ResearchTask.lease_generation).where(ResearchTask.id == task_id)
    )
    generation = row.scalar_one_or_none()
    logger.info(
        "租约领取成功: task_id=%s, worker=%s, generation=%s, ttl=%ss",
        task_id, worker_id, generation, ttl_seconds,
    )
    return generation


async def renew_task_lease(
    session: AsyncSession,
    task_id: str,
    worker_id: str,
    generation: int,
    ttl_seconds: int | None = None,
) -> bool:
    """Worker 续租：仅当前 owner 且 generation 匹配时可续（DATABASE.md §8）。"""
    if ttl_seconds is None:
        ttl_seconds = settings.RESEARCH_TASK_LEASE_TTL_SECONDS
    now = datetime.now(timezone.utc)
    result = await session.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.lease_owner == worker_id,
            ResearchTask.lease_generation == generation,
            ResearchTask.status.in_(["pending", "running"]),
            ResearchTask.cancel_requested_at.is_(None),
        )
        .values(lease_expires_at=now + timedelta(seconds=ttl_seconds))
    )
    return result.rowcount > 0


async def release_task_lease(
    session: AsyncSession,
    task_id: str,
    worker_id: str,
) -> bool:
    """Worker 释放租约：清除 lease_owner / lease_expires_at（仅 owner 匹配时）。"""
    result = await session.execute(
        sa_update(ResearchTask)
        .where(ResearchTask.id == task_id, ResearchTask.lease_owner == worker_id)
        .values(lease_owner=None, lease_expires_at=None)
    )
    return result.rowcount > 0


async def is_step_commit_allowed(
    session: AsyncSession,
    task_id: str,
    worker_id: str,
    generation: int,
) -> bool:
    """Step 提交条件校验（DATABASE.md §5.3 / §8）。

    Task 的 lease_owner 与 lease_generation 仍匹配、Task 未终止或取消，
    才允许写业务结果并标记 Step completed。过期 Worker 的迟到提交返回 False。
    """
    row = await session.execute(
        sa_select(
            ResearchTask.lease_owner,
            ResearchTask.lease_generation,
            ResearchTask.status,
            ResearchTask.cancel_requested_at,
        ).where(ResearchTask.id == task_id)
    )
    task_row = row.one_or_none()
    if task_row is None:
        return False
    owner, gen, status, cancel_at = task_row
    return (
        owner == worker_id
        and gen == generation
        and status in ("pending", "running")
        and cancel_at is None
    )


class TaskLockHandle:
    """任务级幂等锁句柄，负责获取、租约刷新与释放。"""

    def __init__(self, task_id: str):
        self._task_id = task_id
        self._acquired = False
        self._refresh_task: asyncio.Task | None = None

    @property
    def acquired(self) -> bool:
        return self._acquired

    async def acquire(self, ttl: int | None = None) -> bool:
        """获取任务级锁；成功后启动租约刷新。"""
        if self._acquired:
            return True
        locked = await acquire_task_lock_async(self._task_id, ttl=ttl)
        if locked:
            self._acquired = True
            self._start_refresh()
        return locked

    async def release(self) -> None:
        """停止刷新并释放任务级锁。"""
        self._stop_refresh()
        if self._acquired:
            await release_task_lock_async(self._task_id)
            self._acquired = False

    def _start_refresh(self) -> None:
        """启动后台协程定期刷新锁 TTL。"""
        if self._refresh_task is not None:
            return
        interval = settings.CELERY_LOCK_REFRESH_INTERVAL

        async def _refresh_loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    refreshed = await refresh_task_lock_async(self._task_id)
                    if not refreshed:
                        logger.warning(
                            "任务级锁续期失败（锁已不存在），停止刷新: task_id=%s",
                            self._task_id,
                        )
                        break
                except Exception:
                    logger.exception("任务级锁续期异常: task_id=%s", self._task_id)

        self._refresh_task = asyncio.create_task(_refresh_loop())
        logger.debug(
            "启动任务级锁租约刷新: task_id=%s, interval=%ss",
            self._task_id, interval,
        )

    def _stop_refresh(self) -> None:
        """停止租约刷新协程。"""
        if self._refresh_task is None:
            return
        self._refresh_task.cancel()
        self._refresh_task = None
        logger.debug("停止任务级锁租约刷新")


async def start_research_task(
    task: ResearchTask,
    session: AsyncSession,
    sse_bridge: SSEBridge,
    lock_handle: TaskLockHandle,
) -> bool:
    """启动研究任务：pending → running CAS，获取任务锁，修正 total_steps，发送 task.created。

    Args:
        task: 已加载的 ResearchTask
        session: 异步 DB session
        sse_bridge: SSE 桥接器
        lock_handle: 任务锁句柄

    Returns:
        True: 成功启动/恢复并持有锁
        False: 未成功启动（锁被占或 CAS 失败）
    """
    task_id = str(task.id)
    await session.refresh(task)
    current_status = task.status
    now = datetime.now(timezone.utc)

    if current_status == "pending":
        locked = await lock_handle.acquire()
        if not locked:
            logger.warning(
                "正常路径获取任务级锁失败，尝试强制释放残留锁: task_id=%s", task_id
            )
            await release_task_lock_async(task_id)
            locked = await lock_handle.acquire()
            if not locked:
                logger.error(
                    "强制释放残留锁后仍无法获取任务级锁，但仍提交 running "
                    "交由超时监察者兜底: task_id=%s", task_id
                )

        result = await session.execute(
            sa_update(ResearchTask)
            .where(ResearchTask.id == task_id, ResearchTask.status == "pending")
            .values(status="running", started_at=now)
        )
        if result.rowcount == 0:
            logger.warning(
                "CAS 失败：任务状态已非 pending，释放锁并跳过: task_id=%s", task_id
            )
            await lock_handle.release()
            return False
        await session.commit()
        await session.refresh(task)

        if not locked:
            logger.warning(
                "task 已进入 running 但未持有锁，等待超时监察者介入: task_id=%s", task_id
            )
            return False

    elif current_status == "running":
        logger.warning("任务处于 running，进入崩溃恢复路径: task_id=%s", task_id)
        if not await lock_handle.acquire():
            logger.warning(
                "崩溃恢复时任务级锁已被占用，跳过: task_id=%s", task_id
            )
            return False

    else:
        logger.warning(
            "任务状态不支持启动: task_id=%s, status=%s", task_id, current_status
        )
        return False

    # 修正旧任务 total_steps
    if task.total_steps != len(PHASE_ORDER):
        task.total_steps = len(PHASE_ORDER)
        await session.commit()
        await session.refresh(task)
        logger.info(
            "修正 total_steps: task_id=%s, old=%s → new=%d",
            task_id, task.total_steps, len(PHASE_ORDER)
        )

    # 仅正常启动路径发送 task.created
    if current_status == "pending":
        await sse_bridge.publish(EVENT_TASK_CREATED, {
            "task_id": task_id,
            "status": "running",
            "created_at": task.created_at.isoformat() if task.created_at else None,
        })

    emit_task_status_transition("running")

    logger.info(
        "任务启动: task_id=%s, mode=%s",
        task_id, "recovery" if current_status == "running" else "normal",
    )
    return True


async def cas_update_task_status(
    session: AsyncSession,
    task_id: str,
    old_statuses: list[str],
    **values: Any,
) -> bool:
    """CAS 更新任务状态（仅当当前状态在 old_statuses 中时才更新）。"""
    result = await session.execute(
        sa_update(ResearchTask)
        .where(ResearchTask.id == task_id, ResearchTask.status.in_(old_statuses))
        .values(**values)
    )
    await session.flush()
    return result.rowcount > 0


async def load_task_steps(session: AsyncSession, task_id: str) -> list[ResearchStep]:
    """显式加载任务全部 Step，覆盖 identity map 中过期对象。"""
    try:
        result = await session.execute(
            sa_select(ResearchStep)
            .where(ResearchStep.task_id == task_id)
            .order_by(ResearchStep.started_at)
            .execution_options(populate_existing=True)
        )
        steps = list(result.scalars().all())
        if steps:
            return steps
    except Exception as exc:
        logger.debug(
            "显式查询 Step 失败，回退到 task.steps: task_id=%s, error=%s",
            task_id, exc,
        )

    task = await session.get(ResearchTask, task_id)
    if task is not None:
        await session.refresh(task, ["steps"])
        return list(task.steps) if hasattr(task, "steps") else []
    return []


async def emergency_fail_task(
    session: AsyncSession,
    task_id: str,
    error_code: str = "E3999",
    error_message: str = "未预期的内部错误，请稍后重试",
    recoverable: bool = False,
) -> bool:
    """在 session 内将任务状态 CAS 更新为 failed。"""
    now = datetime.now(timezone.utc)
    updated = await cas_update_task_status(
        session,
        task_id,
        old_statuses=["pending", "running"],
        status="failed",
        completed_at=now,
        error_code=error_code,
        error_message=error_message,
        recoverable=recoverable,
    )
    if updated:
        logger.warning(
            "紧急失败写入成功: task_id=%s, error_code=%s", task_id, error_code
        )
    else:
        logger.warning(
            "紧急失败写入 CAS 失败，任务已非 pending/running: task_id=%s", task_id
        )
    return updated
