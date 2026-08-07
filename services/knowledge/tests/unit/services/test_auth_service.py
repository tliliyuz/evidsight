"""认证 Service 单元测试 — Mock DB session"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.exceptions import (
    InvalidCredentialsException,
    UserDisabledException,
    UsernameExistsException,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse, UserSummary
from app.services.auth_service import get_current_user_profile, login, register
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)

    # Mock refresh 模拟 DB 回填 id/role/status/created_at（status 由 DB server_default 置为 active）
    async def _refresh(instance):
        instance.id = instance.id or 1
        instance.role = instance.role or "user"
        instance.status = instance.status or "active"
        instance.created_at = instance.created_at or datetime.now(timezone.utc)

    session.refresh.side_effect = _refresh
    return session


def _make_mock_result(value):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, mock_db):
        mock_db.execute.return_value = _make_mock_result(None)

        result = await register(mock_db, "newuser", "123456")

        assert isinstance(result, UserResponse)
        assert result.username == "newuser"
        assert result.id == 1
        assert result.role == "user"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        added_user = mock_db.add.call_args[0][0]
        assert isinstance(added_user, User)
        assert added_user.username == "newuser"
        assert added_user.password_hash.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, mock_db):
        existing = User(username="existing", password_hash="xxx")
        mock_db.execute.return_value = _make_mock_result(existing)

        with pytest.raises(UsernameExistsException) as exc:
            await register(mock_db, "existing", "123456")
        assert exc.value.error_code == "E5001"
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_strong_password(self, mock_db):
        mock_db.execute.return_value = _make_mock_result(None)

        result = await register(mock_db, "user1", "P@ssw0rd!长密码")

        assert result.username == "user1"
        assert result.id == 1
        mock_db.add.assert_called_once()


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, mock_db):
        from app.core.security import hash_password

        user = User(
            id=1,
            platform_user_id="550e8400-e29b-41d4-a716-446655440000",
            username="test",
            password_hash=hash_password("correct"),
        )
        mock_db.execute.return_value = _make_mock_result(user)

        result = await login(mock_db, "test", "correct")

        assert isinstance(result, TokenResponse)
        # 验证 token 可解码且 claims 正确（非仅 truthy 断言）
        from app.core.security import decode_access_token

        access_payload = decode_access_token(result.access_token)
        assert access_payload["sub"] is not None
        assert "exp" in access_payload
        assert result.token_type == "bearer"
        assert result.expires_in == 15 * 60  # 15 分钟

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, mock_db):
        from app.core.security import hash_password

        user = User(username="test", password_hash=hash_password("correct"))
        mock_db.execute.return_value = _make_mock_result(user)

        with pytest.raises(InvalidCredentialsException) as exc:
            await login(mock_db, "test", "wrong")
        assert exc.value.error_code == "E5002"

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, mock_db):
        mock_db.execute.return_value = _make_mock_result(None)

        with pytest.raises(InvalidCredentialsException) as exc:
            await login(mock_db, "ghost", "any")
        assert exc.value.error_code == "E5002"

    @pytest.mark.asyncio
    async def test_login_token_jwt_format(self, mock_db):
        """验证 access_token 和 refresh_token 为合法 JWT 格式"""
        from app.core.security import decode_access_token, hash_password

        user = User(
            id=1,
            platform_user_id="550e8400-e29b-41d4-a716-446655440000",
            username="u",
            password_hash=hash_password("p"),
        )
        mock_db.execute.return_value = _make_mock_result(user)

        result = await login(mock_db, "u", "p")

        # access_token JWT 格式 + 可解码
        assert "." in result.access_token
        assert len(result.access_token) > 20
        access_payload = decode_access_token(result.access_token)
        assert "sub" in access_payload
        assert "exp" in access_payload

        # refresh_token JWT 格式 + 可解码
        assert "." in result.refresh_token
        assert len(result.refresh_token) > 20
        from app.core.security import decode_refresh_token

        refresh_payload = decode_refresh_token(result.refresh_token)
        assert "sub" in refresh_payload


class TestRegisterV1:
    """IA-017：register_v1 返回 UserSummary，id 为 Platform User UUID，不含内部 users.id。"""

    @pytest.mark.asyncio
    async def test_register_v1_returns_uuid_summary(self, mock_db):
        import uuid

        from app.services.auth_service import register_v1

        mock_db.execute.return_value = _make_mock_result(None)

        result = await register_v1(mock_db, "newuser", "123456")

        assert isinstance(result, UserSummary)
        assert result.username == "newuser"
        assert result.role == "user"
        assert result.status == "active"
        # id 为合法 Platform User UUID（非内部 users.id 整数）
        uuid.UUID(str(result.id))
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_v1_duplicate_raises(self, mock_db):
        from app.services.auth_service import register_v1

        existing = User(username="existing", password_hash="xxx")
        mock_db.execute.return_value = _make_mock_result(existing)

        with pytest.raises(UsernameExistsException) as exc:
            await register_v1(mock_db, "existing", "123456")
        assert exc.value.error_code == "E5001"
        mock_db.add.assert_not_called()


class TestGetCurrentUserProfile:
    """IA-014：/me 数据来源与用户不存在/禁用分支。"""

    PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"

    @pytest.mark.asyncio
    async def test_active_user_returns_db_fields(self, mock_db):
        """UserSummary 的 id/username/role/status 均来自数据库当前状态，不拼装 Token Claim。"""
        import uuid

        user = User(
            platform_user_id=self.PLATFORM_UUID,
            username="db-user",
            role="admin",
            status="active",
            password_hash="x",
        )
        mock_db.execute.return_value = _make_mock_result(user)

        result = await get_current_user_profile(mock_db, self.PLATFORM_UUID)

        assert isinstance(result, UserSummary)
        assert result.id == uuid.UUID(self.PLATFORM_UUID)
        assert result.username == "db-user"
        assert result.role == "admin"
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_user_not_found_raises_5010(self, mock_db):
        """用户不存在统一返回 401 E5010。"""
        mock_db.execute.return_value = _make_mock_result(None)

        with pytest.raises(UserDisabledException) as exc:
            await get_current_user_profile(mock_db, self.PLATFORM_UUID)
        assert exc.value.error_code == "E5010"

    @pytest.mark.asyncio
    async def test_disabled_user_raises_5010(self, mock_db):
        """用户已禁用统一返回 401 E5010。"""
        user = User(
            platform_user_id=self.PLATFORM_UUID,
            username="disabled-user",
            role="user",
            status="disabled",
            password_hash="x",
        )
        mock_db.execute.return_value = _make_mock_result(user)

        with pytest.raises(UserDisabledException) as exc:
            await get_current_user_profile(mock_db, self.PLATFORM_UUID)
        assert exc.value.error_code == "E5010"


class TestLoginLogSensitivity:
    """M1 退出门禁 6：登录路径日志不得包含密码或 Token 明文。

    目标行为由 auth_service 既有实现满足（登录成功只记录 user_id，失败不记录
    请求凭证）；本测试在日志中出现密码或 Token 明文时 RED，防止未来回归。
    """

    @pytest.mark.asyncio
    async def test_login_success_log_omits_password_and_tokens(self, mock_db, caplog):
        import logging

        from app.core.security import hash_password

        password = "P@ssw0rd!门禁明文"
        user = User(
            id=1,
            platform_user_id="550e8400-e29b-41d4-a716-446655440000",
            username="secret_user",
            password_hash=hash_password(password),
        )
        mock_db.execute.return_value = _make_mock_result(user)

        with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
            result = await login(mock_db, "secret_user", password)

        logged = [r.getMessage() for r in caplog.records]
        for secret in (password, result.access_token, result.refresh_token):
            assert all(secret not in msg for msg in logged), f"登录成功日志泄露敏感明文: {secret}"

    @pytest.mark.asyncio
    async def test_login_failure_log_omits_password(self, mock_db, caplog):
        import logging

        from app.core.security import hash_password

        wrong = "错误密码明文"
        user = User(username="test", password_hash=hash_password("correct"))
        mock_db.execute.return_value = _make_mock_result(user)

        with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
            with pytest.raises(InvalidCredentialsException):
                await login(mock_db, "test", wrong)

        logged = [r.getMessage() for r in caplog.records]
        assert all(wrong not in msg for msg in logged), "登录失败日志泄露密码明文"
