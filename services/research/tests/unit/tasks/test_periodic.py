"""Celery Beat 定时清理任务单元测试。

覆盖 cleanup_old_research_tasks / cleanup_stale_refresh_tokens / _check_tasks_exist
的核心分支，并验证定时任务代码不再使用 asyncio.run()。
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import periodic as periodic_module
from app.tasks.periodic import (
    cleanup_old_research_tasks,
    cleanup_stale_refresh_tokens,
    _check_tasks_exist,
)


# ═══════════════════════════════════════════════════════════════════════
# 测试工具
# ═══════════════════════════════════════════════════════════════════════


class _MockSessionFactory:
    """模拟 async_session_factory：callable 返回自身作为 async 上下文管理器。"""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fresh_loop():
    """每个测试独立的新事件循环，结束后关闭。"""
    loop = asyncio.new_event_loop()
    yield loop
    try:
        if not loop.is_closed():
            loop.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# cleanup_old_research_tasks
# ═══════════════════════════════════════════════════════════════════════


class TestCleanupOldResearchTasks:
    def test_清理成功_返回删除计数与孤儿锁数(self, fresh_loop):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock(return_value=None)

        with patch("app.tasks.periodic.get_worker_loop", return_value=fresh_loop):
            with patch(
                "app.tasks.periodic.async_session_factory",
                new=_MockSessionFactory(mock_session),
            ):
                with patch("app.tasks.periodic._cleanup_orphan_task_locks", return_value=2):
                    with patch.object(
                        cleanup_old_research_tasks, "retry", side_effect=Exception("should not retry")
                    ):
                        result = cleanup_old_research_tasks(max_age_days=30)

        assert result == {"deleted_tasks": 3, "orphan_lock_keys_removed": 2}
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    def test_DB异常_触发Celery重试(self, fresh_loop):
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB 连接失败"))
        mock_session.commit = AsyncMock(return_value=None)

        retry_exc = RuntimeError("retry")

        with patch("app.tasks.periodic.get_worker_loop", return_value=fresh_loop):
            with patch(
                "app.tasks.periodic.async_session_factory",
                new=_MockSessionFactory(mock_session),
            ):
                with patch.object(cleanup_old_research_tasks, "retry", return_value=retry_exc):
                    with pytest.raises(RuntimeError) as exc_info:
                        cleanup_old_research_tasks(max_age_days=30)

        assert exc_info.value is retry_exc


# ═══════════════════════════════════════════════════════════════════════
# cleanup_stale_refresh_tokens
# ═══════════════════════════════════════════════════════════════════════


class TestCleanupStaleRefreshTokens:
    def test_清理成功_返回删除计数(self, fresh_loop):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock(return_value=None)

        with patch("app.tasks.periodic.get_worker_loop", return_value=fresh_loop):
            with patch(
                "app.tasks.periodic.async_session_factory",
                new=_MockSessionFactory(mock_session),
            ):
                with patch.object(
                    cleanup_stale_refresh_tokens, "retry", side_effect=Exception("should not retry")
                ):
                    result = cleanup_stale_refresh_tokens(max_age_days=90)

        assert result == {"deleted_tokens": 5}
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════
# _check_tasks_exist
# ═══════════════════════════════════════════════════════════════════════


class TestCheckTasksExist:
    def test_只返回存在的任务ID(self, fresh_loop):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [("task-1",), ("task-3",)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.tasks.periodic.get_worker_loop", return_value=fresh_loop):
            with patch(
                "app.tasks.periodic.async_session_factory",
                new=_MockSessionFactory(mock_session),
            ):
                result = _check_tasks_exist({"task-1", "task-2", "task-3"})

        assert result == {"task-1", "task-3"}

    def test_空集合_返回空集合(self, fresh_loop):
        with patch("app.tasks.periodic.get_worker_loop", return_value=fresh_loop):
            result = _check_tasks_exist(set())

        assert result == set()


# ═══════════════════════════════════════════════════════════════════════
# 源码约束：禁止在 periodic 中使用 asyncio.run
# ═══════════════════════════════════════════════════════════════════════


def test_periodic源码_未使用_asyncio_run():
    """确保 periodic.py 不再调用 asyncio.run()，避免 loop 被反复关闭。"""
    source = inspect.getsource(periodic_module)
    assert "asyncio.run(" not in source
