"""Research Access Token 验证单元测试。"""

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.security import decode_access_token
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
