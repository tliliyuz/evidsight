"""task_lifecycle 共享原语单元测试。"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.models.enums import STEP_TYPE_ENUM
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.services.task_lifecycle import (
    TaskLeaseHandle,
    emergency_fail_task,
    load_task_steps,
    start_research_task,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SessionContextManager:
    """把已存在 db_session 包装成 async_session_factory 上下文管理器。"""

    def __init__(self, session):
        self._session = session
        self._original_commit = session.commit
        session.commit = session.flush

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        self._session.commit = self._original_commit
        return False


def _session_factory(db_session):
    def factory():
        return _SessionContextManager(db_session)

    return factory


class TestTaskLeaseHandle:
    async def test_续租_纯DB不依赖Redis(self, db_session, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-1",
            user_id=user.id,
            topic="test",
            requirements={},
            status="running",
            lease_owner="worker-1",
            lease_generation=1,
            # §13.1/评审 🔴1：健康 Worker 在租约未过期时续租；过期租约不可被复活
            lease_expires_at=_now() + timedelta(seconds=10),
        )
        db_session.add(task)
        await db_session.flush()

        handle = TaskLeaseHandle("task-1")
        handle.bind_lease("worker-1", 1, ttl_seconds=120)
        with patch(
            "app.services.task_lifecycle.async_session_factory",
            new=_session_factory(db_session),
        ):
            ok = await handle.renew_lease()

        assert ok is True
        await db_session.refresh(task)
        assert task.lease_expires_at > _now() + timedelta(seconds=100)

        with patch(
            "app.services.task_lifecycle.async_session_factory",
            new=_session_factory(db_session),
        ):
            await handle.release()

    async def test_续租失败_置lease_lost(self, db_session, seeded_user):
        user, _ = seeded_user
        # 任务已被新 Worker 接管（owner/generation 不匹配）→ 旧 Worker 续租失败
        task = ResearchTask(
            id="task-1b",
            user_id=user.id,
            topic="test",
            requirements={},
            status="running",
            lease_owner="worker-new",
            lease_generation=2,
            lease_expires_at=_now() + timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        handle = TaskLeaseHandle("task-1b")
        handle.bind_lease("worker-old", 1, ttl_seconds=120)
        with patch(
            "app.services.task_lifecycle.async_session_factory",
            new=_session_factory(db_session),
        ):
            ok = await handle.renew_lease()

        assert ok is False
        assert handle.lease_lost is True


class TestStartResearchTask:
    async def test_pending任务启动_单条条件更新领取租约(
        self, db_session: AsyncSession, seeded_user, monkeypatch
    ):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-1",
            user_id=user.id,
            topic="test",
            requirements={},
            status="pending",
            total_steps=0,
        )
        db_session.add(task)
        await db_session.flush()

        # 单元测试中避免真实 commit 破坏事务隔离：将 commit 重定向为 flush
        monkeypatch.setattr(db_session, "commit", db_session.flush)

        sse = AsyncMock()
        handle = TaskLeaseHandle("task-1")
        try:
            started = await start_research_task(task, db_session, sse, handle)

            assert started is True
            assert task.status == "running"
            assert task.total_steps == len(STEP_TYPE_ENUM)
            assert handle.lease_bound is True
            await db_session.refresh(task)
            assert task.lease_owner == handle.worker_id
            assert task.lease_generation == 1
            sse.publish.assert_awaited_once()
        finally:
            with patch(
                "app.services.task_lifecycle.async_session_factory",
                new=_session_factory(db_session),
            ):
                await handle.release()

    async def test_终态任务不启动(self, db_session: AsyncSession, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-2",
            user_id=user.id,
            topic="test",
            requirements={},
            status="completed",
        )
        db_session.add(task)
        await db_session.flush()

        sse = AsyncMock()
        handle = TaskLeaseHandle("task-2")
        started = await start_research_task(task, db_session, sse, handle)

        assert started is False

    async def test_已请求取消_不启动(self, db_session: AsyncSession, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-2b",
            user_id=user.id,
            topic="test",
            requirements={},
            status="pending",
            cancel_requested_at=_now(),
        )
        db_session.add(task)
        await db_session.flush()

        sse = AsyncMock()
        handle = TaskLeaseHandle("task-2b")
        started = await start_research_task(task, db_session, sse, handle)

        assert started is False


class TestLoadTaskSteps:
    async def test_加载任务steps(self, db_session: AsyncSession, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-3", user_id=user.id, topic="t", requirements={}, status="running"
        )
        db_session.add(task)
        await db_session.flush()

        step1 = ResearchStep(task_id="task-3", step_type="planning", status="completed")
        step2 = ResearchStep(task_id="task-3", step_type="search", status="running")
        db_session.add_all([step1, step2])
        await db_session.flush()

        steps = await load_task_steps(db_session, "task-3")
        assert len(steps) == 2
        assert {s.step_type for s in steps} == {"planning", "search"}


class TestEmergencyFailTask:
    async def test_running任务被标记为failed(self, db_session: AsyncSession, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-4", user_id=user.id, topic="t", requirements={}, status="running"
        )
        db_session.add(task)
        await db_session.flush()

        updated = await emergency_fail_task(db_session, "task-4", "E3999", "test error")
        assert updated is True
        await db_session.refresh(task)
        assert task.status == "failed"
        assert task.error_code == "E3999"

    async def test_completed任务不覆盖(self, db_session: AsyncSession, seeded_user):
        user, _ = seeded_user
        task = ResearchTask(
            id="task-5", user_id=user.id, topic="t", requirements={}, status="completed"
        )
        db_session.add(task)
        await db_session.flush()

        updated = await emergency_fail_task(db_session, "task-5")
        assert updated is False
