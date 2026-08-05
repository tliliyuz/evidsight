"""Research 单元测试共享 fixtures。

仅作用于 tests/unit/ 目录（不覆盖 tests/contract/，后者必须保持独立运行）。
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _identity_gate_ok(monkeypatch):
    """默认把身份状态检查设为通过，避免既有 create_task 测试发起真实 HTTP。

    IA-012 门禁测试会显式覆盖本 fixture，把 check_user_status 替换为抛错 mock。
    raising=False：RED 阶段（check_user_status 尚不存在）也能干净装配。
    """
    from unittest.mock import AsyncMock

    from app.services import research_service

    async def _ok(user_id: str):
        return None

    monkeypatch.setattr(
        research_service, "check_user_status", AsyncMock(side_effect=_ok), raising=False,
    )


@pytest.fixture(autouse=True)
def _celery_delay_noop():
    """单元测试无 Redis broker：将 API 层 Celery 任务分发替换为 no-op。

    否则 POST 创建任务的 API 测试会在 _execute_research_task.delay() 处
    （celery/backends/redis.py kombu retry_over_time）无限重试挂起。
    显式断言 delay 调用与否的用例（如 direct_answer 测试）在本 fixture 之上
    再 patch，内层 mock 生效，断言不受影响。
    """
    from app.api import research as research_api

    original = research_api._execute_research_task
    research_api._execute_research_task = MagicMock()
    yield
    research_api._execute_research_task = original
