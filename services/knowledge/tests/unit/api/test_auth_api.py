"""认证 API 接口测试 — 使用 TestClient 走完整 HTTP 链路"""
import uuid
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import pytest

from app.schemas.auth import UserResponse, TokenResponse, UserSummary
from app.core.exceptions import UsernameExistsException, InvalidCredentialsException


def _make_user_response(username="testuser"):
    return UserResponse(
        id=1, username=username, role="user",
        created_at=datetime.now(timezone.utc)
    )


def _make_token_response():
    return TokenResponse(access_token="fake-token", refresh_token="fake-refresh-token", expires_in=900)


class TestRegisterAPI:
    @pytest.mark.asyncio
    async def test_register_success(self, async_client):
        with patch("app.api.auth.register", new_callable=AsyncMock) as mock_reg:
            mock_reg.return_value = _make_user_response("newuser")

            response = await async_client.post(
                "/api/auth/register",
                json={"username": "newuser", "password": "123456"}
            )

        assert response.status_code == 201
        body = response.json()
        assert body["code"] == "0"
        assert body["message"] == "注册成功"
        assert body["data"]["username"] == "newuser"
        assert body["data"]["role"] == "user"

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, async_client):
        with patch("app.api.auth.register", new_callable=AsyncMock) as mock_reg:
            mock_reg.side_effect = UsernameExistsException("existing")

            response = await async_client.post(
                "/api/auth/register",
                json={"username": "existing", "password": "123456"}
            )

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "E5001"

    @pytest.mark.asyncio
    async def test_register_username_too_short(self, async_client):
        response = await async_client.post(
            "/api/auth/register",
            json={"username": "a", "password": "123456"}
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_register_password_too_short(self, async_client):
        response = await async_client.post(
            "/api/auth/register",
            json={"username": "test", "password": "123"}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_register_missing_username(self, async_client):
        response = await async_client.post(
            "/api/auth/register",
            json={"password": "123456"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password(self, async_client):
        response = await async_client.post(
            "/api/auth/register",
            json={"username": "test"}
        )
        assert response.status_code == 422


class TestLoginAPI:
    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        with patch("app.api.auth.login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = _make_token_response()

            response = await async_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "correct"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "0"
        assert body["message"] == "登录成功"
        assert body["data"]["access_token"] == "fake-token"
        assert body["data"]["refresh_token"] == "fake-refresh-token"
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["expires_in"] == 900

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client):
        with patch("app.api.auth.login", new_callable=AsyncMock) as mock_login:
            mock_login.side_effect = InvalidCredentialsException()

            response = await async_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "wrongpw"}
            )

        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "E5002"

    @pytest.mark.asyncio
    async def test_login_empty_username(self, async_client):
        """空用户名被 LoginRequest min_length=2 拒绝"""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "", "password": "correct"}
        )

        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_login_missing_password(self, async_client):
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "test"}
        )
        assert response.status_code == 422


class TestV1RegisterAPI:
    """IA-017：POST /api/v1/auth/register 返回 UserSummary，id 为 Platform User UUID。

    目标态：响应体直接返回 UserSummary（id=UUID 字符串、含 status），
    不含旧 UserResponse 的 created_at 或内部 users.id。
    旧 POST /api/auth/register 保留为迁移期兼容入口。
    """

    V1_UUID = "550e8400-e29b-41d4-a716-446655440010"

    @pytest.mark.asyncio
    async def test_v1_register_returns_uuid_user_summary(self, async_client):
        with patch("app.api.auth.register_v1", new_callable=AsyncMock, create=True) as mock_reg:
            mock_reg.return_value = UserSummary(
                id=self.V1_UUID, username="newuser", role="user", status="active",
            )
            response = await async_client.post(
                "/api/v1/auth/register",
                json={"username": "newuser", "password": "123456"},
            )

        assert response.status_code == 201
        data = response.json()
        # id 为合法 UUID 字符串，非内部 users.id 整数
        uuid.UUID(data["id"])
        assert data["id"] == self.V1_UUID
        assert data["username"] == "newuser"
        assert data["role"] == "user"
        assert data["status"] == "active"
        # 不含旧 UserResponse 的 created_at 字段
        assert "created_at" not in data

    @pytest.mark.asyncio
    async def test_v1_register_duplicate_username(self, async_client):
        with patch("app.api.auth.register_v1", new_callable=AsyncMock, create=True) as mock_reg:
            mock_reg.side_effect = UsernameExistsException("existing")
            response = await async_client.post(
                "/api/v1/auth/register",
                json={"username": "existing", "password": "123456"},
            )

        assert response.status_code == 409
        assert response.json()["code"] == "E5001"

    @pytest.mark.asyncio
    async def test_v1_register_username_too_short(self, async_client):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "a", "password": "123456"}
        )
        assert response.status_code == 422


class TestMeAPI:
    PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"

    @pytest.mark.asyncio
    async def test_me_returns_user_summary(self, async_client, auth_headers):
        """IA-014：/api/v1/auth/me 直接返回 UserSummary，id 为合法 UUID 字符串。"""
        with patch("app.api.auth.get_current_user_profile", new_callable=AsyncMock) as mock_profile:
            mock_profile.return_value = UserSummary(
                id=self.PLATFORM_UUID,
                username="testuser",
                role="user",
                status="active",
            )
            response = await async_client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert uuid.UUID(body["id"])
        assert body["id"] == self.PLATFORM_UUID
        assert body["username"] == "testuser"
        assert body["role"] == "user"
        assert body["status"] == "active"

    @pytest.mark.asyncio
    async def test_me_without_auth_returns_401(self, async_client):
        """未携带 Token 访问 /me 返回 401 E5004。"""
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["code"] == "E5004"

    @pytest.mark.asyncio
    async def test_me_disabled_user_returns_401(self, async_client, auth_headers):
        """IA-014：用户被禁用时 /me 返回 401 E5010。"""
        from app.main import app
        from app.dependencies import get_current_user
        from app.core.exceptions import UserDisabledException

        async def _disabled_user():
            raise UserDisabledException()

        app.dependency_overrides[get_current_user] = _disabled_user
        try:
            response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 401
        assert response.json()["code"] == "E5010"


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_no_auth_header_returns_401(self, async_client):
        response = await async_client.get("/api/knowledge-bases")
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "E5004"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, async_client):
        response = await async_client.get(
            "/api/knowledge-bases",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "E5004"

    @pytest.mark.asyncio
    async def test_public_route_skips_middleware(self, async_client):
        """公开路由 OPTIONS /api/auth/login 被中间件放行（不要求 Token）"""
        response = await async_client.options("/api/auth/login")
        # OPTIONS 被中间件直接放行，FastAPI 返回 405 Method Not Allowed（因为没有注册 OPTIONS 路由）
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_options_preflight_skipped(self, async_client):
        """OPTIONS 预检请求被中间件直接放行，FastAPI 无 OPTIONS 路由返回 405"""
        response = await async_client.options("/api/knowledge-bases")
        # 中间件放行 OPTIONS → 路由系统无 OPTIONS handler → 405 Method Not Allowed
        assert response.status_code == 405
