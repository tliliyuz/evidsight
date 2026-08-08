"""启动时 / Worker 就绪时过时任务恢复测试 — recover_stale_tasks（纯 DB lease）。

覆盖场景：
- 无 running 任务
- 有过时任务（租约过期/为空）→ 重新投递
- 有效租约存在 → 不过时不投递
- 非 running 状态不投递
- 启动恢复被禁用
- 查询异常不阻塞
- 投递异常不阻塞后续任务
- 手动治理 / 启动 / Beat 共用同一恢复服务
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.main import _recover_stale_tasks
from app.models.research_task import ResearchTask
from app.tasks.recovery import recover_stale_tasks


class _SessionContextManager:
    """把已存在的 db_session 包装成 async_session_factory 的上下文管理器。

    Recovery 内部会调用 session.commit()；为避免提交外层测试事务造成跨测试数据泄漏，
    进入上下文时把 commit 重定向为 flush（恢复逻辑写入仍生效，随测试结束统一回滚）。
    """

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
    """返回一个复用测试 db_session 的 session_factory。"""

    def factory():
        return _SessionContextManager(db_session)

    return factory


async def _seed_user(db_session):
    """返回 Knowledge 用户 UUID，不在 Research 持久化。"""
    return SimpleNamespace(id="00000000-0000-4000-8000-000000000001")


class TestRecoverStaleTasks:
    """recover_stale_tasks 核心逻辑测试（纯 DB lease，无 Redis）。"""

    @pytest.mark.asyncio
    async def test_无running任务_不投递(self, db_session):
        await _seed_user(db_session)

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_有过时running任务_租约为空_重新投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="过时任务",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_owner=None,
            lease_expires_at=None,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == [str(task.id)]
        mock_task.delay.assert_called_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_有过时running任务_租约过期_重新投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="过时任务",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_owner="worker-old",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            lease_generation=1,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == [str(task.id)]
        mock_task.delay.assert_called_once_with(str(task.id))

    @pytest.mark.asyncio
    async def test_有效租约存在_不过时不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="有效租约",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_owner="worker-1",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
            lease_generation=1,
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_非running状态_不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="已完成任务",
            requirements={"task_type": "analysis"},
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_启动恢复被禁用_不查询不投递(self, db_session):
        user = await _seed_user(db_session)
        task = ResearchTask(
            user_id=user.id,
            topic="禁用恢复",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        db_session.add(task)
        await db_session.flush()

        with patch("app.tasks.recovery.settings.STARTUP_RECOVERY_ENABLED", False):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                recovered = await recover_stale_tasks()

        assert recovered == []
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_查询异常_不阻塞不抛异常(self, db_session):
        with patch(
            "app.tasks.recovery.async_session_factory",
            side_effect=RuntimeError("DB 连接失败"),
        ):
            recovered = await recover_stale_tasks()

        assert recovered == []

    @pytest.mark.asyncio
    async def test_投递异常_不阻塞后续任务(self, db_session):
        user = await _seed_user(db_session)
        task1 = ResearchTask(
            user_id=user.id,
            topic="任务1",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_owner=None,
            lease_expires_at=None,
        )
        task2 = ResearchTask(
            user_id=user.id,
            topic="任务2",
            requirements={"task_type": "analysis"},
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
            lease_owner=None,
            lease_expires_at=None,
        )
        db_session.add(task1)
        db_session.add(task2)
        await db_session.flush()

        with patch("app.tasks.recovery.async_session_factory", new=_session_factory(db_session)):
            with patch("app.tasks.research_task.execute_research_task") as mock_task:
                mock_task.delay.side_effect = [RuntimeError("投递失败"), None]
                recovered = await recover_stale_tasks()

        assert mock_task.delay.call_count == 2
        assert recovered == [str(task2.id)]


class TestMainStartupRecovery:
    """app.main._recover_stale_tasks 包装器测试。"""

    @pytest.mark.asyncio
    async def test_main包装器调用recover_stale_tasks(self):
        with patch("app.main.recover_stale_tasks", return_value=["task-1"]) as mock_recover:
            await _recover_stale_tasks()

        # 启动恢复调用同一恢复服务（无 check_lock，纯 DB lease）
        mock_recover.assert_awaited_once_with()
