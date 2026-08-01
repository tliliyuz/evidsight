"""Pydantic Schema 校验测试 — 覆盖 app/schemas/auth.py 全部请求/响应模型。

对齐 TESTING_STRATEGY.md §4.8。
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


class TestRegisterRequest:
    """RegisterRequest 字段校验"""

    def test_正常注册_username和password合法(self):
        req = RegisterRequest(username="testuser", password="pass123")
        assert req.username == "testuser"
        assert req.password == "pass123"

    def test_username少于2字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="a", password="pass123")

    def test_username超过64字符抛出ValidationError(self):
        long_name = "a" * 65
        with pytest.raises(ValidationError):
            RegisterRequest(username=long_name, password="pass123")

    def test_password少于6字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", password="12345")

    def test_password超过128字符抛出ValidationError(self):
        long_pass = "x" * 129
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", password=long_pass)

    def test_纯数字用户名抛出ValidationError(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(username="12345", password="pass123")
        errors = exc_info.value.errors()
        assert any("纯数字" in e["msg"] for e in errors)

    def test_纯空格用户名抛出ValidationError(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(username="   ", password="pass123")
        errors = exc_info.value.errors()
        assert any("不能为空" in e["msg"] for e in errors)

    def test_username边界值2字符合法(self):
        req = RegisterRequest(username="ab", password="pass123")
        assert req.username == "ab"

    def test_username边界值64字符合法(self):
        req = RegisterRequest(username="a" * 64, password="pass123")
        assert req.username == "a" * 64

    def test_password边界值6字符合法(self):
        req = RegisterRequest(username="testuser", password="123456")
        assert req.password == "123456"

    def test_password边界值128字符合法(self):
        req = RegisterRequest(username="testuser", password="x" * 128)
        assert req.password == "x" * 128


class TestLoginRequest:
    """LoginRequest 字段校验"""

    def test_正常登录请求(self):
        req = LoginRequest(username="testuser", password="pass123")
        assert req.username == "testuser"
        assert req.password == "pass123"

    def test_username少于2字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="a", password="pass123")

    def test_password少于6字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="testuser", password="12345")


class TestRefreshRequest:
    """RefreshRequest"""

    def test_正常刷新请求(self):
        req = RefreshRequest(refresh_token="some-jwt-token")
        assert req.refresh_token == "some-jwt-token"


class TestLogoutRequest:
    """LogoutRequest"""

    def test_正常退出请求(self):
        req = LogoutRequest(refresh_token="some-token-to-revoke")
        assert req.refresh_token == "some-token-to-revoke"


class TestChangePasswordRequest:
    """ChangePasswordRequest"""

    def test_正常改密请求(self):
        req = ChangePasswordRequest(old_password="oldpass", new_password="newpass")
        assert req.old_password == "oldpass"
        assert req.new_password == "newpass"

    def test_旧密码少于6字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="12345", new_password="newpass")

    def test_新密码少于6字符抛出ValidationError(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password="oldpass", new_password="12345")


class TestTokenResponse:
    """TokenResponse"""

    def test_正常Token响应(self):
        from datetime import datetime, timezone
        resp = TokenResponse(
            access_token="at.jwt.token",
            refresh_token="rt.jwt.token",
            token_type="bearer",
            expires_in=900,
        )
        assert resp.access_token == "at.jwt.token"
        assert resp.refresh_token == "rt.jwt.token"
        assert resp.token_type == "bearer"
        assert resp.expires_in == 900


class TestUserResponse:
    """UserResponse — from_attributes 支持"""

    def test_正常用户响应(self):
        from datetime import datetime, timezone
        resp = UserResponse(
            id=1,
            username="testuser",
            role="user",
            created_at=datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert resp.id == 1
        assert resp.username == "testuser"
        assert resp.role == "user"
        assert resp.created_at.year == 2026
