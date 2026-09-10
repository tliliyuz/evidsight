"""AC-004 恢复演练脚本入口回归测试。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import verify_ac004_recovery_drill as script


@pytest.mark.asyncio
async def test_run_以任务ID调用单任务演练(monkeypatch):
    """run() 解析任务后只把 task_id 传给拥有独立会话的 _drill_one。"""

    session = SimpleNamespace(flush=AsyncMock())

    @asynccontextmanager
    async def session_factory():
        yield session

    async def drill_one(task_id: str) -> tuple[bool, str]:
        assert task_id == "task-1"
        return True, "ok"

    monkeypatch.setattr(
        script,
        "_parse_args",
        lambda: SimpleNamespace(tasks="eval.json", samples=1),
    )
    monkeypatch.setattr(script, "_load_eval_set", lambda _path: [{"id": "case-1"}])
    monkeypatch.setattr(
        script,
        "_resolve_task",
        AsyncMock(return_value=SimpleNamespace(id="task-1")),
    )
    monkeypatch.setattr(script, "_drill_one", drill_one)
    monkeypatch.setattr(script, "async_session_factory", session_factory)
    monkeypatch.setattr(script.subprocess, "check_output", lambda *_args, **_kwargs: "abc123")

    assert await script.run() == 0
    session.flush.assert_awaited_once()
