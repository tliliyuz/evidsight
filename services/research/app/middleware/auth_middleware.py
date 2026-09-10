"""JWT 验证中间件 — 从 Authorization header 提取并验证 Bearer Token，将当前用户写入 request.state

使用纯 ASGI 中间件（非 BaseHTTPMiddleware），以便正确返回 JSON 错误响应。

[Deviation] ResearchMind 认证中间件设计：
- 过期 token 返回 E1003（AUTH_TOKEN_EXPIRED），其余验证失败返回 E1004（AUTH_TOKEN_INVALID）
- detail 为结构化 JSON 对象（error_type + error_description）
"""

from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.core.api_response import error_envelope
from app.core.security import decode_access_token_with_status

# 不需要认证的公开路由
_PUBLIC_PATHS = {
    "/api/health",
    "/api/health/workers",
}


def _is_public(path: str) -> bool:
    """判断路径是否为公开路由（无需认证）。"""
    if path == settings.METRICS_ENDPOINT:
        return True
    return path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi.json")


def _invalid_token_response(
    request: Request, detail: str, code: str = "E1004", message: str = "Token 无效或格式错误"
) -> JSONResponse:
    """构造 401 认证错误响应。

    code/message 由调用方按失败原因决定：默认 E1004（无效）；已过期传入
    E1003「Token 已过期」——前端仅在收到 AUTH_TOKEN_EXPIRED 时静默刷新。
    """
    if request.url.path.startswith("/api/v1/"):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        return JSONResponse(
            status_code=401,
            content=error_envelope(
                code=code,
                message=message,
                request_id=request_id,
                status_code=401,
                retryable=False,
            ),
            headers={"X-Request-ID": request_id},
        )
    return JSONResponse(
        status_code=401,
        content={
            "code": code,
            "message": message,
            "detail": {"error_type": "InvalidToken", "error_description": detail},
        },
    )


class AuthMiddleware:
    """纯 ASGI 中间件 — JWT 认证。

    对非公开路由：
    1. 提取 Authorization: Bearer <token> header
    2. 调用 decode_access_token_with_status() 验证 JWT
    3. 将 user_id / username / role 写入 request.state
    4. 过期返回 401 E1003，其余验证失败返回 401 E1004

    路由处理器通过 dependencies.get_current_user() 读取 request.state
    并做额外的 DB 状态校验（用户是否被禁用）。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        # OPTIONS 预检 + 公开路由跳过认证
        if request.method == "OPTIONS" or _is_public(request.url.path):
            await self.app(scope, receive, send)
            return

        # 提取 Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            response = _invalid_token_response(
                request, "缺少 Authorization header 或格式不是 Bearer"
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        payload, status = decode_access_token_with_status(token)

        if status == "expired":
            # 已过期：返回 E1003，前端据此静默刷新（对齐 ERROR_CODE_MAP E1003 契约）。
            response = _invalid_token_response(
                request, "Token 已过期", code="E1003", message="Token 已过期"
            )
            await response(scope, receive, send)
            return

        if status == "invalid":
            response = _invalid_token_response(request, "Token 解析失败或已过期")
            await response(scope, receive, send)
            return

        # 将用户信息写入 request.state（异常防护）
        try:
            request.state.platform_user_id = payload["sub"]
            request.state.user_id = payload["sub"]
        except (KeyError, ValueError, TypeError):
            response = _invalid_token_response(request, "Token payload 缺少 sub 字段或格式异常")
            await response(scope, receive, send)
            return

        request.state.username = payload.get("username")
        request.state.role = payload.get("role")

        await self.app(scope, receive, send)
