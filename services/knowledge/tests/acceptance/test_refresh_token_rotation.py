"""M1 IA-003/IA-004/IA-011：Refresh Token Family 与原子轮换验收测试。"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.security import create_refresh_token, decode_refresh_token, hash_password, hash_token
from app.models.refresh_token import RefreshToken
from app.models.user import User

PLATFORM_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
FAMILY_ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 1
    user.platform_user_id = PLATFORM_USER_ID
    user.username = "m1-user"
    user.password_hash = hash_password("correct-password")
    user.role = "user"
    user.status = "active"
    return user


@pytest.mark.asyncio
async def test_ia003_登录创建family并让refresh_token携带平台用户与family身份():
    """删除 Family 创建或退回 BIGINT sub 时必须失败。"""
    from app.models.refresh_token_family import RefreshTokenFamily
    from app.services.auth_service import login

    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(_user()))

    result = await login(db, "m1-user", "correct-password")

    added = [call.args[0] for call in db.add.call_args_list]
    family = next(item for item in added if isinstance(item, RefreshTokenFamily))
    token = next(item for item in added if isinstance(item, RefreshToken))
    payload = decode_refresh_token(result.refresh_token)

    assert family.user_id == PLATFORM_USER_ID
    assert token.family_id == family.id
    assert payload["sub"] == PLATFORM_USER_ID
    assert payload["family_id"] == family.id


@pytest.mark.asyncio
async def test_ia003_刷新锁定旧token并只建立一个已记录的后继():
    """移除行锁、轮换时间或后继引用时必须失败。"""
    from app.models.refresh_token_family import RefreshTokenFamily
    from app.services.auth_service import refresh

    old_token_text = create_refresh_token(PLATFORM_USER_ID, FAMILY_ID)
    family = RefreshTokenFamily(
        id=FAMILY_ID,
        user_id=PLATFORM_USER_ID,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    old_token = RefreshToken(
        id=41,
        family_id=FAMILY_ID,
        token_hash=hash_token(old_token_text),
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(old_token), _scalar_result(_user())])
    db.get = AsyncMock(return_value=family)

    result = await refresh(db, old_token_text)

    statement = db.execute.call_args_list[0].args[0]
    assert statement._for_update_arg is not None
    successors = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], RefreshToken)
    ]
    assert len(successors) == 1
    successor = successors[0]
    assert successor.family_id == FAMILY_ID
    assert old_token.rotated_at is not None
    assert old_token.replaced_by is successor
    assert family.last_rotated_at == old_token.rotated_at
    assert decode_refresh_token(result.refresh_token)["family_id"] == FAMILY_ID


@pytest.mark.asyncio
async def test_ia004_重放已轮换token撤销family并记录安全事件():
    """移除 Family 撤销、审计、请求关联或安全状态提交时必须失败。"""
    from app.core.exceptions import TokenLeakDetectedException
    from app.core.logging_config import request_id_var
    from app.models.refresh_token_family import RefreshTokenFamily
    from app.services.auth_service import refresh

    token_text = create_refresh_token(PLATFORM_USER_ID, FAMILY_ID)
    family = RefreshTokenFamily(
        id=FAMILY_ID,
        user_id=PLATFORM_USER_ID,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    old_token = RefreshToken(
        id=41,
        family_id=FAMILY_ID,
        token_hash=hash_token(token_text),
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        rotated_at=datetime.now(timezone.utc),
        replaced_by_id=42,
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(old_token), _scalar_result(family)])

    request_id_token = request_id_var.set("ia004-request-id")
    try:
        with pytest.raises(TokenLeakDetectedException):
            await refresh(db, token_text)
    finally:
        request_id_var.reset(request_id_token)

    assert family.revoked_at is not None
    assert family.revoke_reason == "refresh_token_replay"
    added = [call.args[0] for call in db.add.call_args_list]
    audit_events = [item for item in added if type(item).__name__ == "IdentityAuditEvent"]
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event.user_id == PLATFORM_USER_ID
    assert event.event_type == "refresh_replay"
    assert event.request_id == "ia004-request-id"
    assert event.outcome == "denied"
    assert event.details == {"family_id": FAMILY_ID, "action": "family_revoked"}
    assert token_text not in str(event.details)
    assert hash_token(token_text) not in str(event.details)
    assert not any(isinstance(item, RefreshToken) for item in added)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ia004_普通撤销token不误判为重放():
    """将普通撤销误报为重放或写入审计时必须失败。"""
    from app.core.exceptions import RefreshTokenRevokedException
    from app.services.auth_service import refresh

    token_text = create_refresh_token(PLATFORM_USER_ID, FAMILY_ID)
    revoked_token = RefreshToken(
        id=41,
        family_id=FAMILY_ID,
        token_hash=hash_token(token_text),
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=datetime.now(timezone.utc),
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(revoked_token))

    with pytest.raises(RefreshTokenRevokedException):
        await refresh(db, token_text)

    assert not db.add.called
    db.commit.assert_not_awaited()
