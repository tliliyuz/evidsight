"""Research Access Token 验证单元测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from app.config import settings
from app.core.security import decode_access_token, decode_access_token_with_status
from app.middleware.auth_middleware import AuthMiddleware
from httpx import ASGITransport, AsyncClient
from jose import jwt

PLATFORM_USER_ID = "550e8400-e29b-41d4-a716-446655440000"


def _token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
        "aud": ["evidsight-knowledge", settings.EVIDSIGHT_RESEARCH_JWT_AUDIENCE],
        "sub": PLATFORM_USER_ID,
        "role": "user",
        "token_type": "access",
        "jti": "research-unit-token",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
    }
    payload.update(overrides)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def test_有效token返回platform_user_uuid():
    assert decode_access_token(_token())["sub"] == PLATFORM_USER_ID


def test_错误audience被拒绝():
    assert decode_access_token(_token(aud=["evidsight-knowledge"])) == {}


def test_错误issuer被拒绝():
    assert decode_access_token(_token(iss="other")) == {}


def test_refresh类型被拒绝():
    assert decode_access_token(_token(token_type="refresh")) == {}


def test_非法uuid被拒绝():
    assert decode_access_token(_token(sub="1")) == {}


def test_过期token被拒绝():
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert decode_access_token(_token(exp=expired)) == {}


def test_伪造或空token被拒绝():
    assert decode_access_token("not.a.valid.jwt") == {}
    assert decode_access_token("") == {}


# ── decode_access_token_with_status：区分「有效 / 过期 / 无效」 ──
# 对齐 ERROR_CODE_MAP E1003→AUTH_TOKEN_EXPIRED / E1004→AUTH_TOKEN_INVALID：
# 中间件须把「已过期」与「无效」区分，供前端收到 AUTH_TOKEN_EXPIRED 时静默刷新
# （此前统一 E1004 导致前端把过期当致命错误直接登出，见 CHANGELOG 2026-08-12）。


def test_decode_with_status_有效token_ok():
    payload, status = decode_access_token_with_status(_token())
    assert status == "ok"
    assert payload["sub"] == PLATFORM_USER_ID


def test_decode_with_status_过期token_expired():
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    payload, status = decode_access_token_with_status(_token(exp=expired))
    assert status == "expired"
    assert payload == {}


def test_decode_with_status_无效token_invalid():
    payload, status = decode_access_token_with_status("not.a.valid.jwt")
    assert status == "invalid"
    assert payload == {}


# ── AuthMiddleware 隔离测试（纯 ASGI 包装，不依赖 DB） ──


async def _dummy_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _middleware_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=AuthMiddleware(_dummy_app)), base_url="http://test"
    )


@pytest.mark.asyncio
async def test_middleware_过期token_v1返回AUTH_TOKEN_EXPIRED():
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with _middleware_client() as client:
        resp = await client.get(
            "/api/v1/research/tasks",
            headers={"Authorization": f"Bearer {_token(exp=expired)}"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_middleware_无效token_v1返回AUTH_TOKEN_INVALID():
    async with _middleware_client() as client:
        resp = await client.get(
            "/api/v1/research/tasks",
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_TOKEN_INVALID"
