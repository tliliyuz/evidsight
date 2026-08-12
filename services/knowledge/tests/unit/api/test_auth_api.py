"""认证 API 接口测试 — 使用 TestClient 走完整 HTTP 链路"""

import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, patch

import pytest
from app.config import settings
from app.core.exceptions import (
    InvalidCredentialsException,
    RefreshTokenExpiredException,
    TokenLeakDetectedException,
    UserDisabledException,
    UsernameExistsException,
)
from app.schemas.auth import TokenResponse, UserResponse, UserSummary


def _cookies_from_response(response):
    """从 Set-Cookie 响应头解析 Cookie（Secure Cookie 在 HTTP 下不回传，改读响应头）。"""
    cookies = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        cookies.load(value)
    return cookies


def _make_user_response(username="testuser"):
    return UserResponse(id=1, username=username, role="user", created_at=datetime.now(timezone.utc))


def _make_token_response():
    return TokenResponse(
        access_token="fake-token", refresh_token="fake-refresh-token", expires_in=900
    )


class TestRegisterAPI:
    @pytest.mark.asyncio
    async def test_register_success(self, async_client):
        with patch("app.api.auth.register", new_callable=AsyncMock) as mock_reg:
            mock_reg.return_value = _make_user_response("newuser")

            response = await async_client.post(
                "/api/auth/register", json={"username": "newuser", "password": "123456"}
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
                "/api/auth/register", json={"username": "existing", "password": "123456"}
            )

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "E5001"

    @pytest.mark.asyncio
    async def test_register_username_too_short(self, async_client):
        response = await async_client.post(
            "/api/auth/register", json={"username": "a", "password": "123456"}
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_register_password_too_short(self, async_client):
        response = await async_client.post(
            "/api/auth/register", json={"username": "test", "password": "123"}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_register_missing_username(self, async_client):
        response = await async_client.post("/api/auth/register", json={"password": "123456"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password(self, async_client):
        response = await async_client.post("/api/auth/register", json={"username": "test"})
        assert response.status_code == 422


class TestLoginAPI:
    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        with patch("app.api.auth.login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = _make_token_response()

            response = await async_client.post(
                "/api/auth/login", json={"username": "testuser", "password": "correct"}
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
                "/api/auth/login", json={"username": "testuser", "password": "wrongpw"}
            )

        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "E5002"

    @pytest.mark.asyncio
    async def test_login_empty_username(self, async_client):
        """空用户名被 LoginRequest min_length=2 拒绝"""
        response = await async_client.post(
            "/api/auth/login", json={"username": "", "password": "correct"}
        )

        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_login_missing_password(self, async_client):
        response = await async_client.post("/api/auth/login", json={"username": "test"})
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
                id=self.V1_UUID,
                username="newuser",
                role="user",
                status="active",
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
        assert response.json()["error"]["error_code"] == "AUTH_USERNAME_CONFLICT"

    @pytest.mark.asyncio
    async def test_v1_register_username_too_short(self, async_client):
        response = await async_client.post(
            "/api/v1/auth/register", json={"username": "a", "password": "123456"}
        )
        assert response.status_code == 422


class TestV1LoginAPI:
    """IA-015：POST /api/v1/auth/login 使用 HttpOnly Refresh Cookie + double-submit CSRF。

    目标态（ADR-006 / IDENTITY_AND_ACCESS.md §4.2）：
    - 登录成功设置 HttpOnly Refresh Cookie 与 非 HttpOnly CSRF Cookie；
    - 响应体返回 access_token + 最小用户摘要（UserSummary），绝不含 refresh_token 明文；
    - 凭证错误 / 禁用用户返回 401 且不设置任何 Cookie。
    """

    PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440011"

    @pytest.mark.asyncio
    async def test_login_success_sets_cookies_without_refresh_in_body(self, async_client):
        with patch("app.api.auth.login_v1", new_callable=AsyncMock, create=True) as mock_login_v1:
            mock_login_v1.return_value = (
                "fake-access-token",
                "fake-refresh-token",
                UserSummary(
                    id=self.PLATFORM_UUID,
                    username="testuser",
                    role="user",
                    status="active",
                ),
            )
            response = await async_client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "correct"},
            )

        assert response.status_code == 200
        mock_login_v1.assert_awaited_once()

        # 响应体：access_token + 用户摘要，不含 refresh_token 明文
        body = response.json()
        assert body["access_token"] == "fake-access-token"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert "refresh_token" not in body
        user = body["user"]
        uuid.UUID(user["id"])
        assert user["id"] == self.PLATFORM_UUID
        assert user["username"] == "testuser"
        assert user["role"] == "user"
        assert user["status"] == "active"
        assert "created_at" not in user

        # Refresh Cookie：HttpOnly + Secure + SameSite=lax + Path=/（__Host- 强制 Path=/）
        cookies = _cookies_from_response(response)
        refresh = cookies[settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME]
        assert refresh.value == "fake-refresh-token"
        assert refresh["path"] == "/"
        assert refresh["httponly"]
        assert refresh["secure"]
        assert refresh["samesite"] == "lax"
        assert refresh["max-age"] == str(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)

        # CSRF Cookie：非 HttpOnly（前端 JS 可读），Path=/ 使 SPA 页面可读取
        csrf = cookies[settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME]
        assert csrf.value
        assert csrf["path"] == "/"
        assert not csrf["httponly"]
        assert csrf["secure"]

    @pytest.mark.asyncio
    async def test_login_wrong_credentials_401_no_cookie(self, async_client):
        with patch("app.api.auth.login_v1", new_callable=AsyncMock, create=True) as mock_login_v1:
            mock_login_v1.side_effect = InvalidCredentialsException()
            response = await async_client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "wrongpw"},
            )

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_INVALID_CREDENTIALS"
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_login_disabled_user_401_no_cookie(self, async_client):
        with patch("app.api.auth.login_v1", new_callable=AsyncMock, create=True) as mock_login_v1:
            mock_login_v1.side_effect = UserDisabledException()
            response = await async_client.post(
                "/api/v1/auth/login",
                json={"username": "disabled", "password": "correct"},
            )

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_login_missing_password_422_no_cookie(self, async_client):
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "testuser"},
        )

        assert response.status_code == 422
        assert not response.headers.get_list("set-cookie")


class TestV1RefreshAPI:
    """IA-015：POST /api/v1/auth/refresh — HttpOnly Cookie + double-submit CSRF 轮换。

    目标态（ADR-006 / IDENTITY_AND_ACCESS.md §4.2）：
    - verify_csrf 先于任何 Refresh Token 处理；CSRF 失败返回 E5004 且不进入轮换、不设 Cookie；
    - 从 HttpOnly Refresh Cookie 读取 Token，成功后同一响应轮换 Refresh/CSRF Cookie；
    - 响应体返回 access_token，不含 refresh_token 明文；
    - 重放、Family 撤销、用户禁用、过期等刷新失败返回对应 401 并清除 Cookie。
    """

    REFRESH_COOKIE = settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME
    CSRF_COOKIE = settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME
    CSRF_TOKEN = "test-csrf-token"

    def _post_refresh(
        self,
        async_client,
        *,
        refresh_token="old-refresh-token",
        csrf_header=True,
        csrf_cookie=True,
        origin=None,
    ):
        cookies = {}
        if csrf_cookie:
            cookies[self.CSRF_COOKIE] = self.CSRF_TOKEN
        if refresh_token is not None:
            cookies[self.REFRESH_COOKIE] = refresh_token
        headers = {}
        if csrf_header:
            headers["X-CSRF-Token"] = self.CSRF_TOKEN
        if origin:
            headers["Origin"] = origin
        return async_client.post("/api/v1/auth/refresh", cookies=cookies, headers=headers)

    @pytest.mark.asyncio
    async def test_refresh_success_rotates_cookies(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.return_value = TokenResponse(
                access_token="new-access-token",
                refresh_token="new-refresh-token",
                expires_in=900,
            )
            response = await self._post_refresh(async_client)

        assert response.status_code == 200
        mock_refresh.assert_awaited_once()
        assert mock_refresh.await_args is not None
        # 服务层拿到的是 Refresh Cookie 中的旧 Token（未被 body 覆盖）
        assert mock_refresh.await_args.args[1] == "old-refresh-token"

        # 响应体：access_token，不含 refresh_token 明文
        body = response.json()
        assert body["access_token"] == "new-access-token"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert "refresh_token" not in body

        # 新 Refresh Cookie（轮换值）+ 新 CSRF Cookie 在同一响应设置
        cookies = _cookies_from_response(response)
        refresh = cookies[self.REFRESH_COOKIE]
        assert refresh.value == "new-refresh-token"
        assert refresh["httponly"]
        assert refresh["path"] == "/"
        assert refresh["secure"]
        assert refresh["samesite"] == "lax"
        csrf = cookies[self.CSRF_COOKIE]
        assert csrf.value
        assert not csrf["httponly"]
        assert csrf["path"] == "/"

    # ---- CSRF 失败：不进入轮换、不设 Cookie ----

    @pytest.mark.asyncio
    async def test_refresh_csrf_header_missing_401_no_rotation(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            response = await self._post_refresh(async_client, csrf_header=False)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
        mock_refresh.assert_not_awaited()
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_refresh_csrf_cookie_missing_401_no_rotation(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            response = await self._post_refresh(async_client, csrf_cookie=False)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
        mock_refresh.assert_not_awaited()
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_refresh_csrf_mismatch_401_no_rotation(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            response = await async_client.post(
                "/api/v1/auth/refresh",
                cookies={
                    self.CSRF_COOKIE: "cookie-token",
                    self.REFRESH_COOKIE: "old-refresh-token",
                },
                headers={"X-CSRF-Token": "header-token"},
            )

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
        mock_refresh.assert_not_awaited()
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_refresh_origin_not_in_whitelist_401_no_rotation(self, async_client, monkeypatch):
        monkeypatch.setattr(
            settings,
            "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS",
            "https://app.example.com",
        )
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            response = await self._post_refresh(async_client, origin="https://evil.example.com")

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
        mock_refresh.assert_not_awaited()
        assert not response.headers.get_list("set-cookie")

    # ---- 无 Refresh Cookie ----

    @pytest.mark.asyncio
    async def test_refresh_missing_cookie_401_E5008(self, async_client):
        response = await self._post_refresh(async_client, refresh_token=None)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_REFRESH_INVALID"

    # ---- 刷新失败：对应 401 + 清除 Cookie ----

    @pytest.mark.asyncio
    async def test_refresh_expired_401_clears_cookies(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.side_effect = RefreshTokenExpiredException()
            response = await self._post_refresh(async_client)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_REFRESH_EXPIRED"
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"

    @pytest.mark.asyncio
    async def test_refresh_disabled_user_401_clears_cookies(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.side_effect = UserDisabledException()
            response = await self._post_refresh(async_client)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"

    @pytest.mark.asyncio
    async def test_refresh_replay_401_clears_cookies(self, async_client):
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.side_effect = TokenLeakDetectedException()
            response = await self._post_refresh(async_client)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_REFRESH_REPLAY"
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"


class TestV1LogoutAPI:
    """IA-015：POST /api/v1/auth/logout — Access Token + Refresh Cookie + CSRF 幂等退出。

    目标态（ADR-006 / IDENTITY_AND_ACCESS.md §4.2 / API.md §5）：
    - 需要 Access Token（非公开路由）+ Refresh Cookie + CSRF；
    - verify_csrf 先于任何 Token 处理；CSRF 失败返回 E5004 且不撤销 Token Family；
    - 幂等撤销并清除 Refresh Cookie 与 CSRF Cookie，重复退出不泄露 Token 是否曾有效。
    """

    REFRESH_COOKIE = settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME
    CSRF_COOKIE = settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME
    CSRF_TOKEN = "test-csrf-token"

    def _post_logout(
        self,
        async_client,
        headers=None,
        *,
        refresh_token="old-refresh-token",
        csrf_header=True,
        csrf_cookie=True,
    ):
        cookies = {}
        if csrf_cookie:
            cookies[self.CSRF_COOKIE] = self.CSRF_TOKEN
        if refresh_token is not None:
            cookies[self.REFRESH_COOKIE] = refresh_token
        req_headers = {}
        if csrf_header:
            req_headers["X-CSRF-Token"] = self.CSRF_TOKEN
        if headers:
            req_headers.update(headers)
        return async_client.post("/api/v1/auth/logout", cookies=cookies, headers=req_headers)

    @pytest.mark.asyncio
    async def test_logout_success_204_clears_cookies(self, async_client, auth_headers):
        with patch("app.api.auth.logout", new_callable=AsyncMock, create=True) as mock_logout:
            response = await self._post_logout(async_client, headers=auth_headers)

        assert response.status_code == 204
        mock_logout.assert_awaited_once()
        assert mock_logout.await_args is not None
        # 服务层拿到 Refresh Cookie 中的 Token 与当前用户的 Platform UUID
        assert mock_logout.await_args.args[1] == "old-refresh-token"
        assert mock_logout.await_args.args[2] == "550e8400-e29b-41d4-a716-446655440001"
        # Refresh 与 CSRF Cookie 均被清除
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"

    @pytest.mark.asyncio
    async def test_logout_no_refresh_cookie_idempotent_204(self, async_client, auth_headers):
        """无 Refresh Cookie 时仍幂等返回 204，并清除可能残留的 Cookie。"""
        with patch("app.api.auth.logout", new_callable=AsyncMock, create=True) as mock_logout:
            response = await self._post_logout(
                async_client, headers=auth_headers, refresh_token=None
            )

        assert response.status_code == 204
        mock_logout.assert_not_awaited()
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"

    @pytest.mark.asyncio
    async def test_logout_repeated_idempotent_204(self, async_client, auth_headers):
        with patch("app.api.auth.logout", new_callable=AsyncMock, create=True) as mock_logout:
            r1 = await self._post_logout(async_client, headers=auth_headers)
            r2 = await self._post_logout(async_client, headers=auth_headers)

        assert r1.status_code == 204
        assert r2.status_code == 204
        assert mock_logout.await_count == 2

    @pytest.mark.asyncio
    async def test_logout_csrf_header_missing_401_no_revoke(self, async_client, auth_headers):
        with patch("app.api.auth.logout", new_callable=AsyncMock, create=True) as mock_logout:
            response = await self._post_logout(
                async_client, headers=auth_headers, csrf_header=False
            )

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
        mock_logout.assert_not_awaited()
        assert not response.headers.get_list("set-cookie")

    @pytest.mark.asyncio
    async def test_logout_without_token_401(self, async_client):
        """logout 不是公开路由：未携带 Access Token → 中间件 401 E5004。"""
        response = await self._post_logout(async_client)
        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"


class TestCompatAPI:
    """IA-016：迁移期 body refresh_token 兼容入口（EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT）。

    目标态（ADR-006 / API.md §5 / CONFIGURATION.md §3.1）：
    - 配置开启 + Refresh Cookie 缺失时，回退读取 body refresh_token 并记录弃用日志（不含 Token 明文）；
    - 配置开启 + Cookie 存在时优先 Cookie；
    - 配置关闭时拒绝 body refresh_token（E5008）。
    """

    REFRESH_COOKIE = settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME
    CSRF_COOKIE = settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME
    CSRF_TOKEN = "test-csrf-token"

    @pytest.mark.asyncio
    async def test_refresh_body_compat_enabled_success(self, async_client, monkeypatch):
        """compat 开启 + Cookie 缺失 + body 有效 → 成功并记录弃用日志（不含 Token）。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT", True)
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.return_value = TokenResponse(
                access_token="new-access-token",
                refresh_token="new-refresh-token",
                expires_in=900,
            )
            with patch("app.api.auth.logger", create=True) as mock_logger:
                response = await async_client.post(
                    "/api/v1/auth/refresh",
                    cookies={self.CSRF_COOKIE: self.CSRF_TOKEN},
                    headers={"X-CSRF-Token": self.CSRF_TOKEN},
                    json={"refresh_token": "body-refresh-token"},
                )

        assert response.status_code == 200
        mock_refresh.assert_awaited_once()
        assert mock_refresh.await_args is not None
        # 服务层拿到的是 body 中的 Token
        assert mock_refresh.await_args.args[1] == "body-refresh-token"
        # 弃用日志记录调用，但不得包含 Token 明文
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("弃用" in m for m in warning_msgs)
        assert all("body-refresh-token" not in m for m in warning_msgs)
        # 成功响应仍设置 Cookie（引导迁移到 Cookie 模式）
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE].value == "new-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_body_compat_cookie_preferred(self, async_client, monkeypatch):
        """compat 开启 + Cookie 存在 → 优先 Cookie，不使用 body。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT", True)
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            mock_refresh.return_value = TokenResponse(
                access_token="new-access-token",
                refresh_token="new-refresh-token",
                expires_in=900,
            )
            response = await async_client.post(
                "/api/v1/auth/refresh",
                cookies={
                    self.CSRF_COOKIE: self.CSRF_TOKEN,
                    self.REFRESH_COOKIE: "cookie-refresh-token",
                },
                headers={"X-CSRF-Token": self.CSRF_TOKEN},
                json={"refresh_token": "body-refresh-token"},
            )

        assert response.status_code == 200
        mock_refresh.assert_awaited_once()
        assert mock_refresh.await_args is not None
        assert mock_refresh.await_args.args[1] == "cookie-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_body_compat_disabled_rejected(self, async_client, monkeypatch):
        """compat 关闭 + Cookie 缺失 + body → 401 E5008，不进入轮换。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT", False)
        with patch("app.api.auth.refresh", new_callable=AsyncMock, create=True) as mock_refresh:
            response = await async_client.post(
                "/api/v1/auth/refresh",
                cookies={self.CSRF_COOKIE: self.CSRF_TOKEN},
                headers={"X-CSRF-Token": self.CSRF_TOKEN},
                json={"refresh_token": "body-refresh-token"},
            )

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_REFRESH_INVALID"
        mock_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logout_body_compat_enabled_success(
        self, async_client, auth_headers, monkeypatch
    ):
        """compat 开启 + Cookie 缺失 + body → logout 使用 body token 并 204。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT", True)
        with patch("app.api.auth.logout", new_callable=AsyncMock, create=True) as mock_logout:
            response = await async_client.post(
                "/api/v1/auth/logout",
                cookies={self.CSRF_COOKIE: self.CSRF_TOKEN},
                headers={"X-CSRF-Token": self.CSRF_TOKEN, **auth_headers},
                json={"refresh_token": "body-refresh-token"},
            )

        assert response.status_code == 204
        mock_logout.assert_awaited_once()
        assert mock_logout.await_args is not None
        assert mock_logout.await_args.args[1] == "body-refresh-token"
        cookies = _cookies_from_response(response)
        assert cookies[self.REFRESH_COOKIE]["max-age"] == "0"
        assert cookies[self.CSRF_COOKIE]["max-age"] == "0"


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
        assert response.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"

    @pytest.mark.asyncio
    async def test_me_disabled_user_returns_401(self, async_client, auth_headers):
        """IA-014：用户被禁用时 /me 返回 401 E5010。"""
        from app.core.exceptions import UserDisabledException
        from app.dependencies import get_current_user
        from app.main import app

        async def _disabled_user():
            raise UserDisabledException()

        app.dependency_overrides[get_current_user] = _disabled_user
        try:
            response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 401
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"


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
            "/api/knowledge-bases", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "E5004"

    def _expired_access_token(self, jti: str) -> str:
        """构造签名/Issuer/Audience 均正确、仅 exp 已过的 access token。

        复用 create_access_token 的 Claim 结构；与中间件 decode 使用同一
        settings 密钥，确保唯一失败原因是「过期」。
        """
        from datetime import datetime, timedelta, timezone

        from jose import jwt as jose_jwt

        now = datetime.now(timezone.utc)
        payload = {
            "iss": settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
            "aud": settings.platform_jwt_audiences,
            "sub": "550e8400-e29b-41d4-a716-446655440001",
            "role": "user",
            "token_type": "access",
            "jti": jti,
            "iat": now - timedelta(minutes=20),
            "nbf": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=5),
        }
        return jose_jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @pytest.mark.asyncio
    async def test_expired_token_returns_401_E5003(self, async_client):
        """过期 access token → 401 E5003（legacy 信封）。

        对齐 api_response E5003 契约：中间件必须把「已过期」与「无效」区分，
        供前端收到 AUTH_TOKEN_EXPIRED 时静默刷新。此前中间件对过期统一返回
        E5004，导致前端把过期当致命错误直接登出（见 CHANGELOG 2026-08-12）。
        """
        response = await async_client.get(
            "/api/knowledge-bases",
            headers={"Authorization": f"Bearer {self._expired_access_token('expired-legacy')}"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "E5003"

    @pytest.mark.asyncio
    async def test_expired_token_v1_returns_AUTH_TOKEN_EXPIRED(self, async_client):
        """过期 access token → 401 AUTH_TOKEN_EXPIRED（v1 信封，前端据此静默续期）。"""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self._expired_access_token('expired-v1')}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["error_code"] == "AUTH_TOKEN_EXPIRED"

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
