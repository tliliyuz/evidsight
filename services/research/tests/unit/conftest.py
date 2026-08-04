"""Research 单元测试共享 fixtures。

仅作用于 tests/unit/ 目录（不覆盖 tests/contract/，后者必须保持独立运行）。
"""
import pytest


@pytest.fixture(autouse=True)
def _identity_gate_ok(monkeypatch):
    """默认把身份状态检查设为通过，避免既有 create_task 测试发起真实 HTTP。

    IA-012 门禁测试会显式覆盖本 fixture，把 check_user_status 替换为抛错 mock。
    raising=False：RED 阶段（check_user_status 尚未存在）也能干净装配。
    """
    from unittest.mock import AsyncMock

    from app.services import research_service

    async def _ok(user_id: str):
        return None

    monkeypatch.setattr(
        research_service, "check_user_status", AsyncMock(side_effect=_ok), raising=False,
    )
