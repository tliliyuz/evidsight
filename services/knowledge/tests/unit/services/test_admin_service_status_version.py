"""change_user_status 递增 status_version（DATABASE.md §4.1 语义）"""
import pytest
from unittest.mock import AsyncMock

from app.models.user import User
from app.services.admin_service import change_user_status


@pytest.mark.asyncio
async def test_disable_increments_status_version():
    db = AsyncMock()
    user = User(
        id=1, platform_user_id="550e8400-e29b-41d4-a716-446655440001",
        username="u", password_hash="x", role="user", status="active",
        status_version=0,
    )
    db.get = AsyncMock(return_value=user)
    # 禁用时吊销 refresh_token（避免真实 DB 调用）
    # 注意：change_user_status 函数体内是局部导入 auth_service.revoke_all_user_tokens，
    # 必须 patch 该目标才会生效（用户裁决 2026-08-04）
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.services.auth_service.revoke_all_user_tokens", new=AsyncMock()
    ):
        resp = await change_user_status(db, user.id, "disabled", current_user_id=99)
    assert user.status_version == 1
    assert resp.status == "disabled"


@pytest.mark.asyncio
async def test_noop_status_does_not_increment():
    db = AsyncMock()
    user = User(
        id=1, platform_user_id="550e8400-e29b-41d4-a716-446655440001",
        username="u", password_hash="x", role="user", status="active",
        status_version=3,
    )
    db.get = AsyncMock(return_value=user)
    resp = await change_user_status(db, user.id, "active", current_user_id=99)
    assert user.status_version == 3  # 同状态幂等，不递增
    assert resp.status == "active"
