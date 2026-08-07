"""切片 D —— 租约协议原语验收测试。

对齐 RESEARCH_PIPELINE §13.1 / DATABASE.md §5.1 / §8：
- Worker 领取 Task 使用单条条件更新：非终态、未请求取消、租约为空或已过期；
- 成功后写入 lease_owner、lease_expires_at 并递增 lease_generation；
- 续租只能由当前 owner 执行；
- Step 提交必须与 Task 的 owner/generation 匹配（generation 条件提交）。
"""

from datetime import datetime, timedelta, timezone

from app.models.research_task import ResearchTask
from app.services.task_lifecycle import (
    claim_task_lease,
    is_step_commit_allowed,
    release_task_lease,
    renew_task_lease,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_task(db_session: AsyncSession, task_id: str = "task-lease-1", **kw) -> ResearchTask:
    task = ResearchTask(
        id=task_id,
        user_id="00000000-0000-4000-8000-000000000001",
        topic="租约协议测试",
        requirements={"task_type": "analysis", "max_sources": 10},
        status=kw.pop("status", "pending"),
        **kw,
    )
    db_session.add(task)
    await db_session.flush()
    return task


class TestClaimTaskLease:
    async def test_pending任务_无租约_领取成功_generation为1(self, db_session: AsyncSession):
        task = await _seed_task(db_session)

        generation = await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        assert generation == 1
        await db_session.refresh(task)
        assert task.lease_owner == "worker-1"
        assert task.lease_expires_at is not None
        assert task.lease_expires_at > _now()
        assert task.lease_generation == 1

    async def test_租约有效_其他worker领取失败(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        generation = await claim_task_lease(db_session, str(task.id), "worker-2", ttl_seconds=120)

        assert generation is None
        await db_session.refresh(task)
        assert task.lease_owner == "worker-1"
        assert task.lease_generation == 1

    async def test_租约过期_重新领取_generation递增(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=1)
        # 手动使租约过期
        task.lease_expires_at = _now() - timedelta(seconds=5)
        await db_session.flush()

        generation = await claim_task_lease(db_session, str(task.id), "worker-2", ttl_seconds=120)

        assert generation == 2
        await db_session.refresh(task)
        assert task.lease_owner == "worker-2"
        assert task.lease_generation == 2

    async def test_终态任务_不可领取(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="completed")

        generation = await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        assert generation is None

    async def test_已请求取消_不可领取(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        task.cancel_requested_at = _now()
        await db_session.flush()

        generation = await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        assert generation is None


class TestRenewTaskLease:
    async def test_正确owner_generation_续租成功(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)
        task.lease_expires_at = _now() + timedelta(seconds=10)
        await db_session.flush()

        ok = await renew_task_lease(db_session, str(task.id), "worker-1", 1, ttl_seconds=120)

        assert ok is True
        await db_session.refresh(task)
        assert task.lease_expires_at > _now() + timedelta(seconds=100)

    async def test_错误owner_续租失败(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        ok = await renew_task_lease(db_session, str(task.id), "worker-2", 1, ttl_seconds=120)

        assert ok is False

    async def test_错误generation_续租失败(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        ok = await renew_task_lease(db_session, str(task.id), "worker-1", 999, ttl_seconds=120)

        assert ok is False


class TestReleaseTaskLease:
    async def test_owner释放_清除owner(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        ok = await release_task_lease(db_session, str(task.id), "worker-1")

        assert ok is True
        await db_session.refresh(task)
        assert task.lease_owner is None
        assert task.lease_expires_at is None

    async def test_非owner释放_不生效(self, db_session: AsyncSession):
        task = await _seed_task(db_session)
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        ok = await release_task_lease(db_session, str(task.id), "worker-2")

        assert ok is False
        await db_session.refresh(task)
        assert task.lease_owner == "worker-1"


class TestIsStepCommitAllowed:
    async def test_owner与generation匹配_放行(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="running")
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        allowed = await is_step_commit_allowed(db_session, str(task.id), "worker-1", 1)

        assert allowed is True

    async def test_generation不匹配_拒绝(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="running")
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        allowed = await is_step_commit_allowed(db_session, str(task.id), "worker-1", 999)

        assert allowed is False

    async def test_其他owner_拒绝(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="running")
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)

        allowed = await is_step_commit_allowed(db_session, str(task.id), "worker-2", 1)

        assert allowed is False

    async def test_已请求取消_拒绝(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="running")
        await claim_task_lease(db_session, str(task.id), "worker-1", ttl_seconds=120)
        task.cancel_requested_at = _now()
        await db_session.flush()

        allowed = await is_step_commit_allowed(db_session, str(task.id), "worker-1", 1)

        assert allowed is False

    async def test_终态_拒绝(self, db_session: AsyncSession):
        task = await _seed_task(db_session, status="completed")

        allowed = await is_step_commit_allowed(db_session, str(task.id), "worker-1", 0)

        assert allowed is False
