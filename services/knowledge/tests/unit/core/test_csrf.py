"""CSRF 基础设施测试 — 事件③ Refresh Token Cookie/CSRF 收口（S1）

对齐 ADR-006 与 IDENTITY_AND_ACCESS.md §4.2：
- double-submit CSRF：同时设置非 HttpOnly 的 CSRF Cookie，前端回传同值 `X-CSRF-Token` Header。
- CSRF/Origin 校验必须先于任何 Refresh Token 解码、哈希查询、轮换或撤销执行。
- 校验失败返回统一安全认证错误 E5004，且不得改变 Token Family 或写入重放审计。

覆盖：token 生成、verify_csrf 依赖、Cookie helper 属性。
"""

from http.cookies import SimpleCookie

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.exceptions import InvalidTokenException
from app.core.csrf import (
    clear_auth_cookies,
    generate_csrf_token,
    set_csrf_cookie,
    set_refresh_cookie,
    verify_csrf,
)


# ==================== 辅助函数 ====================

def _cookies_of(response):
    """从 Response.raw_headers 解析全部 Set-Cookie（Starlette 0.46 无 response.cookies）。"""
    cookies = SimpleCookie()
    for name, value in response.raw_headers:
        if name == b"set-cookie":
            cookies.load(value.decode("latin-1"))
    return cookies


def _build_request(cookies=None, headers=None):
    """构造带指定 Cookie 与 Header 的 Starlette Request。"""
    header_bytes = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        header_bytes.append((b"cookie", cookie_header.encode("latin-1")))
    for k, v in (headers or {}).items():
        header_bytes.append((k.lower().encode("latin-1"), str(v).encode("latin-1")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/refresh",
        "raw_path": b"/api/v1/auth/refresh",
        "query_string": b"",
        "root_path": "",
        "headers": header_bytes,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {},
    }
    return Request(scope)


# ==================== token 生成 ====================

class TestGenerateCsrfToken:
    """generate_csrf_token 基础行为"""

    def test_生成非空随机字符串(self):
        token = generate_csrf_token()
        assert token
        assert len(token) >= 32

    def test_两次生成不同(self):
        assert generate_csrf_token() != generate_csrf_token()


# ==================== verify_csrf 依赖 ====================

class TestVerifyCsrf:
    """verify_csrf FastAPI 依赖校验行为（统一安全认证错误 E5004）"""

    @pytest.mark.asyncio
    async def test_Cookie与Header一致通过(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={"X-CSRF-Token": token},
        )
        # 不应抛出任何异常
        await verify_csrf(request)

    @pytest.mark.asyncio
    async def test_Header缺失返回E5004(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        token = generate_csrf_token()
        request = _build_request(cookies={"evidsight_csrf": token}, headers={})
        with pytest.raises(InvalidTokenException) as exc:
            await verify_csrf(request)
        assert exc.value.error_code == "E5004"

    @pytest.mark.asyncio
    async def test_Cookie缺失返回E5004(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        token = generate_csrf_token()
        request = _build_request(cookies={}, headers={"X-CSRF-Token": token})
        with pytest.raises(InvalidTokenException) as exc:
            await verify_csrf(request)
        assert exc.value.error_code == "E5004"

    @pytest.mark.asyncio
    async def test_值不一致返回E5004(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        request = _build_request(
            cookies={"evidsight_csrf": "aaa"},
            headers={"X-CSRF-Token": "bbb"},
        )
        with pytest.raises(InvalidTokenException) as exc:
            await verify_csrf(request)
        assert exc.value.error_code == "E5004"

    # ---- Origin 白名单 ----

    @pytest.mark.asyncio
    async def test_Origin在白名单通过(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS",
            "https://app.example.com, https://admin.example.com",
        )
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={
                "X-CSRF-Token": token,
                "Origin": "https://app.example.com",
            },
        )
        await verify_csrf(request)

    @pytest.mark.asyncio
    async def test_Origin不在白名单返回E5004(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "https://app.example.com")
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={
                "X-CSRF-Token": token,
                "Origin": "https://evil.example.com",
            },
        )
        with pytest.raises(InvalidTokenException) as exc:
            await verify_csrf(request)
        assert exc.value.error_code == "E5004"

    @pytest.mark.asyncio
    async def test_白名单非空但Origin缺失返回E5004(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "https://app.example.com")
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={"X-CSRF-Token": token},
        )
        with pytest.raises(InvalidTokenException) as exc:
            await verify_csrf(request)
        assert exc.value.error_code == "E5004"

    @pytest.mark.asyncio
    async def test_白名单为空时按同站放行(self, monkeypatch):
        """开发环境 allowed_origins 为空时按同站处理，不强制校验 Origin。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={
                "X-CSRF-Token": token,
                "Origin": "http://localhost:5173",
            },
        )
        await verify_csrf(request)

    @pytest.mark.asyncio
    async def test_仅依赖请求与配置不触碰数据库(self, monkeypatch):
        """verify_csrf 只读请求与配置，不依赖 DB 会话，确保不提前触碰 Token 状态。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        token = generate_csrf_token()
        request = _build_request(
            cookies={"evidsight_csrf": token},
            headers={"X-CSRF-Token": token},
        )
        await verify_csrf(request)


# ==================== Cookie helper ====================

class TestCookieHelpers:
    """set_refresh_cookie / set_csrf_cookie / clear_auth_cookies 属性断言"""

    def test_set_refresh_cookie属性(self, monkeypatch):
        # `__Host-` 前缀强制 Path=/（RFC 6265bis §5.5），否则浏览器拒绝 Cookie
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME", "__Host-evidsight_refresh")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH", "/")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE", True)
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE", "lax")
        response = Response()
        set_refresh_cookie(response, "rtoken123")
        morsel = _cookies_of(response)["__Host-evidsight_refresh"]
        assert morsel.value == "rtoken123"
        assert morsel["path"] == "/"
        assert morsel["httponly"]  # HttpOnly 标志已设置
        assert morsel["secure"]  # Secure 标志已设置
        assert morsel["samesite"] == "lax"
        # Cookie 有效期与 Refresh Token 生命周期对齐
        assert morsel["max-age"] == str(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)

    def test_set_refresh_cookie开发模式secure为false(self, monkeypatch):
        """开发环境关闭 Secure 后 Cookie 不含 Secure 标志，便于 HTTP 调试。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME", "dev_refresh")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH", "/")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE", False)
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE", "lax")
        response = Response()
        set_refresh_cookie(response, "rtoken123")
        morsel = _cookies_of(response)["dev_refresh"]
        assert morsel["httponly"]
        assert not morsel["secure"]

    def test_set_csrf_cookie属性(self, monkeypatch):
        """CSRF Cookie 必须非 HttpOnly（前端 JS 可读），Path=/ 使 SPA 页面可经 document.cookie 读取。"""
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE", True)
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE", "lax")
        response = Response()
        set_csrf_cookie(response, "ctoken123")
        morsel = _cookies_of(response)["evidsight_csrf"]
        assert morsel.value == "ctoken123"
        assert morsel["path"] == "/"
        assert not morsel["httponly"]  # 非 HttpOnly，前端 JS 可读
        assert morsel["secure"]
        assert morsel["samesite"] == "lax"

    def test_clear_auth_cookies清除两个Cookie(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME", "__Host-evidsight_refresh")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH", "/")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME", "evidsight_csrf")
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE", True)
        response = Response()
        clear_auth_cookies(response)
        cookies = _cookies_of(response)
        # max-age=0 表示浏览器立即过期删除；删除响应需携带与设置一致的 Secure/HttpOnly
        refresh = cookies["__Host-evidsight_refresh"]
        assert refresh["max-age"] == "0"
        assert refresh["path"] == "/"
        assert refresh["secure"]
        assert refresh["httponly"]
        csrf = cookies["evidsight_csrf"]
        assert csrf["max-age"] == "0"
        assert csrf["path"] == "/"
        assert csrf["secure"]
        assert not csrf["httponly"]
