"""任务生命周期共享原语 —— DB 租约、CAS 状态转换、紧急失败。

本模块抽取 AgentRuntime 与 Recovery Scanner 共用的租约协议与状态原语。

租约协议对齐 RESEARCH_PIPELINE §13.1 / DATABASE.md §8 / ADR-008：
- MySQL 是任务生命周期唯一事实源；Redis/Celery 不作为任务事实来源；
- Worker 领取与续租使用条件更新（WHERE 匹配当前 owner 与 generation）；
- Step 提交必须与 Task 的 owner、generation 同事务校验；
- 失去租约的 Worker 立即停止，不提交业务结果；
- 终态只能由 TaskStateResolver 依据持久 Step/Evidence/Revision 事实推导；
  `emergency_fail_task` 仅限无法进入正常 Resolver 的极端情况（显式分类）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case as sa_case
from sqlalchemy import or_ as sa_or
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import async_session_factory
from app.metrics import emit_task_status_transition
from app.models.enums import STEP_TYPE_ENUM
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    EVENT_TASK_CREATED,
    SSEBridge,
)

logger = logging.getLogger(__name__)

PHASE_ORDER: list[str] = list(STEP_TYPE_ENUM)

# Recovery Scanner 的条件领取 worker 标识（§13.5）。
# Scanner 恢复成功后保留该 handoff 租约直至新 Worker 领取：下一轮扫描条件
# （租约为空或已过期）不命中，保证「只恢复一次」（评审 🔴2）；Worker 领取条件
# 显式接受该标识，避免被 handoff 租约阻塞。
RECOVERY_SCANNER_WORKER_ID = "recovery-scanner"


def new_worker_id() -> str:
    """生成当前执行 Worker 的唯一标识（每次执行新建，用于租约领取/续租/提交校验）。"""
    return f"worker-{uuid.uuid4().hex[:12]}"


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
                # Scanner 恢复后保留的 handoff 租约：新 Worker 可立即接手（§13.5，🔴2）
                ResearchTask.lease_owner == RECOVERY_SCANNER_WORKER_ID,
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
        task_id,
        worker_id,
        generation,
        ttl_seconds,
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
            # §13.1：过期租约不可被旧 Worker 复活；续租必须仍持有未过期租约，
            # 否则崩溃/挂起 Worker 会在 Scanner 接管前自行续约，使恢复失效（评审 🔴1）。
            ResearchTask.lease_expires_at.is_not(None),
            ResearchTask.lease_expires_at > now,
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

    Task 的 lease_owner 与 lease_generation 仍匹配、Task 未终止或取消、
    租约未过期，才允许写业务结果并标记 Step completed。过期 Worker 的
    迟到提交返回 False（§13.1，评审 🔴1）。
    """
    row = await session.execute(
        sa_select(
            ResearchTask.lease_owner,
            ResearchTask.lease_generation,
            ResearchTask.status,
            ResearchTask.cancel_requested_at,
            ResearchTask.lease_expires_at,
        ).where(ResearchTask.id == task_id)
    )
    task_row = row.one_or_none()
    if task_row is None:
        return False
    owner, gen, status, cancel_at, expires_at = task_row
    return (
        owner == worker_id
        and gen == generation
        and status in ("pending", "running")
        and cancel_at is None
        and expires_at is not None
        and expires_at > datetime.now(timezone.utc)
    )


async def is_task_ownership_valid(
    session: AsyncSession,
    task_id: str,
    worker_id: str,
    generation: int,
) -> bool:
    """终态推导前的租约所有权校验（DATABASE.md §8 / §17.12）。

    与 is_step_commit_allowed 的区别：Step 提交必须同时满足「未请求取消」，
    而取消安全停止后的 Resolver 终态推导需要允许 cancel_requested_at 已设置的
    情况，因此本方法只校验 owner/generation 匹配、任务非终态且租约未过期。
    失去租约的 Worker 不推导终态（§13.1，评审 🔴1）。
    """
    row = await session.execute(
        sa_select(
            ResearchTask.lease_owner,
            ResearchTask.lease_generation,
            ResearchTask.status,
            ResearchTask.lease_expires_at,
        ).where(ResearchTask.id == task_id)
    )
    task_row = row.one_or_none()
    if task_row is None:
        return False
    owner, gen, status, expires_at = task_row
    return (
        owner == worker_id
        and gen == generation
        and status in ("pending", "running")
        and expires_at is not None
        and expires_at > datetime.now(timezone.utc)
    )


class TaskLeaseHandle:
    """纯 DB 任务租约句柄 —— 续租与释放，不依赖 Redis（ADR-008 §MySQL 唯一权威）。

    续租失败（租约已被并发 Worker / Scanner 夺走或已过期）置 `lease_lost=True`，
    后续 Provider 调用与 Step 提交必须立即停止，不提交业务结果（§13.1）。
    释放只清当前 owner 的租约（`release_task_lease` 按 owner 匹配），
    旧 Worker 的 finally 不会释放新 Worker 的租约。
    """

    def __init__(self, task_id: str):
        self._task_id = task_id
        self.worker_id: str | None = None
        self.lease_generation: int | None = None
        self._lease_ttl: int | None = None
        self.lease_lost: bool = False
        self._renew_task: asyncio.Task | None = None

    @property
    def lease_bound(self) -> bool:
        """是否已绑定领取后的租约标识（worker_id + generation 齐备）。"""
        return self.worker_id is not None and self.lease_generation is not None

    def bind_lease(self, worker_id: str, generation: int, ttl_seconds: int | None = None) -> None:
        """绑定领取后的租约标识并启动后台续租（§13.1）。"""
        self.worker_id = worker_id
        self.lease_generation = generation
        self._lease_ttl = ttl_seconds
        self.lease_lost = False
        self._start_renewal()

    async def renew_lease(self) -> bool:
        """续租 DB 租约（独立会话，避免与主流程事务冲突；§13.1）。

        续租失败置 `lease_lost=True`，调用方应立即停止后续业务执行。
        """
        worker_id = self.worker_id
        lease_generation = self.lease_generation
        if worker_id is None or lease_generation is None:
            return True
        try:
            async with async_session_factory() as session:
                ok = await renew_task_lease(
                    session,
                    self._task_id,
                    worker_id,
                    lease_generation,
                    ttl_seconds=self._lease_ttl,
                )
                await session.commit()
            if not ok:
                self.lease_lost = True
                # 租约已失效/被接管：立即停止续租协程，避免空转（§13.1 停止后续调用）
                self._stop_renewal()
                logger.warning(
                    "DB 租约续租失败（租约已失效/被接管），Worker 停止执行: "
                    "task_id=%s, worker=%s, generation=%s",
                    self._task_id,
                    self.worker_id,
                    self.lease_generation,
                )
            return ok
        except Exception:
            logger.exception("DB 租约续租异常: task_id=%s", self._task_id)
            # 续租异常与续租返回 False 同权：租约状态未知即视为失去租约，
            # 立即停止后续调用（§13.1，评审 🔴1）。
            self.lease_lost = True
            self._stop_renewal()
            return False

    async def release_lease(self) -> None:
        """释放 DB 租约（仅 owner 匹配生效；DATABASE.md §8）。"""
        try:
            worker_id = self.worker_id
            if worker_id is None or self.lease_generation is None:
                return
            async with async_session_factory() as session:
                await release_task_lease(session, self._task_id, worker_id)
                await session.commit()
        except Exception:
            logger.exception("DB 租约释放异常: task_id=%s", self._task_id)
        finally:
            self.worker_id = None
            self.lease_generation = None
            self._lease_ttl = None
            self.lease_lost = False

    async def release(self) -> None:
        """停止续租协程并释放 DB 租约（仅当前 owner 生效，不影响新 Worker 租约）。"""
        self._stop_renewal()
        await self.release_lease()

    def _start_renewal(self) -> None:
        """启动后台协程定期续租 DB 租约（纯 DB，无 Redis）。"""
        if self._renew_task is not None:
            return
        interval = settings.RESEARCH_TASK_LEASE_RENEW_INTERVAL

        async def _renew_loop():
            while not self.lease_lost:
                await asyncio.sleep(interval)
                if self.lease_lost:
                    break
                if not await self.renew_lease():
                    break

        self._renew_task = asyncio.create_task(_renew_loop())
        logger.debug(
            "启动 DB 租约续租: task_id=%s, interval=%ss",
            self._task_id,
            interval,
        )

    def _stop_renewal(self) -> None:
        """停止租约续租协程。"""
        if self._renew_task is None:
            return
        self._renew_task.cancel()
        self._renew_task = None
        logger.debug("停止 DB 租约续租: task_id=%s", self._task_id)


async def start_research_task(
    task: ResearchTask,
    session: AsyncSession,
    sse_bridge: SSEBridge,
    lease_handle: TaskLeaseHandle,
) -> bool:
    """启动研究任务：pending→running 与 DB lease 领取合并为一次条件更新。

    单条条件更新（DATABASE.md §8 / ADR-008）原子完成，无 Redis：
    - 条件：status IN (pending, running)、未请求取消、租约为空或已过期；
    - 更新：status=running、started_at（pending 首启取 now，崩溃恢复保留原值）、
      lease_owner、lease_expires_at、lease_generation+1。

    领取失败（并发 Worker / Scanner 已持有有效租约、任务已终态或已取消）立即返回
    False，不执行业务步骤、不触碰 Redis。旧 Worker 的迟到提交由 generation 条件拒绝。

    Args:
        task: 已加载的 ResearchTask
        session: 异步 DB session
        sse_bridge: SSE 桥接器
        lease_handle: 纯 DB 租约句柄（绑定 worker_id/generation 供续租与提交校验）

    Returns:
        True: 成功启动/恢复并持有租约
        False: 领取失败（条件不满足），放弃启动
    """
    task_id = str(task.id)
    await session.refresh(task)
    current_status = task.status
    now = datetime.now(timezone.utc)
    ttl = settings.RESEARCH_TASK_LEASE_TTL_SECONDS

    worker_id = new_worker_id()
    result = await session.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status.in_(["pending", "running"]),
            ResearchTask.cancel_requested_at.is_(None),
            sa_or(
                ResearchTask.lease_expires_at.is_(None),
                ResearchTask.lease_expires_at < now,
                # Scanner 恢复后保留的 handoff 租约：新 Worker 可立即接手（§13.5，🔴2）
                ResearchTask.lease_owner == RECOVERY_SCANNER_WORKER_ID,
            ),
        )
        .values(
            status="running",
            # SET 表达式求值于更新前的行：pending 首启取 now，running 恢复保留原 started_at
            started_at=sa_case(
                (ResearchTask.status == "pending", now),
                else_=ResearchTask.started_at,
            ),
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=ttl),
            lease_generation=ResearchTask.lease_generation + 1,
        )
    )
    if result.rowcount == 0:
        logger.warning(
            "租约领取失败（条件不满足，并发 Worker/Scanner 已持有或任务已终态/取消），"
            "放弃启动: task_id=%s, worker=%s",
            task_id,
            worker_id,
        )
        return False

    # 读取递增后的 generation
    row = await session.execute(
        sa_select(ResearchTask.lease_generation).where(ResearchTask.id == task_id)
    )
    generation = row.scalar_one_or_none()
    lease_handle.bind_lease(worker_id, generation, ttl_seconds=ttl)
    await session.commit()
    await session.refresh(task)
    logger.info(
        "Worker 已领取租约: task_id=%s, worker=%s, generation=%s, ttl=%ss",
        task_id,
        worker_id,
        generation,
        ttl,
    )

    # 修正旧任务 total_steps
    if task.total_steps != len(PHASE_ORDER):
        task.total_steps = len(PHASE_ORDER)
        await session.commit()
        await session.refresh(task)
        logger.info(
            "修正 total_steps: task_id=%s, old=%s → new=%d",
            task_id,
            task.total_steps,
            len(PHASE_ORDER),
        )

    # 仅正常启动路径（pending 首启）发送 task.created
    if current_status == "pending":
        await sse_bridge.publish(
            EVENT_TASK_CREATED,
            {
                "task_id": task_id,
                "status": "running",
                "created_at": task.created_at.isoformat() if task.created_at else None,
            },
        )

    emit_task_status_transition("running")

    logger.info(
        "任务启动: task_id=%s, mode=%s",
        task_id,
        "recovery" if current_status == "running" else "normal",
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
            task_id,
            exc,
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
    failure_classification: str = "resolver_unreachable",
) -> bool:
    """在 session 内将任务状态 CAS 更新为 failed。

    ⚠️ 终态纪律（RESEARCH_PIPELINE §13.5）：正常终态只能由 TaskStateResolver 依据
    持久 Step/Evidence/Revision 事实推导。本方法只允许在无法进入正常 Resolver 的
    极端情况（数据库损坏、Resolver 本身不可用）使用，调用处必须提供显式
    `failure_classification`（如 `resolver_unreachable` / `database_corruption`），
    不得用于常规业务失败。错误码固定 E3999。
    """
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
            "紧急失败写入成功（分类=%s，仅限极端情况）: task_id=%s, error_code=%s",
            failure_classification,
            task_id,
            error_code,
        )
    else:
        logger.warning(
            "紧急失败写入 CAS 失败（分类=%s），任务已非 pending/running: task_id=%s",
            failure_classification,
            task_id,
        )
    return updated
