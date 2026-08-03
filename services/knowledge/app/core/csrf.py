"""CSRF 基础设施 — 事件③ Refresh Token Cookie/CSRF 收口

对齐 ADR-006 与 IDENTITY_AND_ACCESS.md §4.2：
- double-submit 模式：Auth API 同时设置非 HttpOnly 的 CSRF Cookie，前端在
  refresh/logout 请求中回传同值 `X-CSRF-Token` Header。
- verify_csrf 必须先于任何 Refresh Token 解码、哈希查询、轮换或撤销执行；
  校验失败抛出统一安全认证错误 E5004，且不得改变 Token Family 或写入重放审计。
- 本模块只依赖请求与配置，不触碰任何 DB / Token 状态。
"""

import secrets

from fastapi import Request
from starlette.responses import Response

from app.config import settings
from app.core.exceptions import InvalidTokenException


def generate_csrf_token() -> str:
    """生成一次性 CSRF Token（无状态 double-submit，不落库）。"""
    return secrets.token_urlsafe(32)


async def verify_csrf(request: Request) -> None:
    """FastAPI 依赖：校验 double-submit CSRF 与 Origin 白名单。

    先于任何 Refresh Token 处理执行；失败时抛出 E5004，绝不改变 Token Family。
    """
    cookie_token = request.cookies.get(settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or not secrets.compare_digest(
        cookie_token, header_token
    ):
        raise InvalidTokenException("CSRF 校验失败")
    allowed_origins = settings.auth_allowed_origins
    if allowed_origins:
        origin = request.headers.get("Origin")
        if not origin or origin not in allowed_origins:
            raise InvalidTokenException("Origin 校验失败")


def set_refresh_cookie(response: Response, token: str) -> None:
    """设置 HttpOnly Refresh Cookie（仅由 Auth API 设置/轮换/清除）。"""
    response.set_cookie(
        key=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH,
        secure=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE,
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    """设置非 HttpOnly CSRF Cookie（前端 JS 可经 document.cookie 读取）。

    Path=/ 使 SPA 页面（根路径）能读取该 Cookie；Secure/SameSite 与 Refresh Cookie 对齐。
    """
    response.set_cookie(
        key=settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
        secure=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE,
        httponly=False,
        samesite=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE,
    )


def clear_auth_cookies(response: Response) -> None:
    """清除 Refresh 与 CSRF Cookie（退出/重放检测/Family 撤销/禁用后刷新失败时调用）。

    删除响应需携带与原 Cookie 一致的 Secure/HttpOnly 属性，否则浏览器会拒绝
    Secure/`__Host-` Cookie 的删除指令，导致旧 Cookie 无法清除。
    """
    secure = settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE
    response.delete_cookie(
        settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME,
        path=settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH,
        secure=secure,
        httponly=True,
    )
    response.delete_cookie(
        settings.EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME,
        path="/",
        secure=secure,
        httponly=False,
    )
