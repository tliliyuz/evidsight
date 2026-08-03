"""JWT 令牌 & 密码哈希 — 使用 python-jose + bcrypt

对齐 ARCHITECTURE.md §9.2：
- access_token：15min 短有效期，用于 API 认证
- refresh_token：7 天长有效期，JWT 格式（含 type='refresh'），SHA-256 哈希存 MySQL
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(user_id: str, role: str) -> str:
    """签发供 Knowledge 与 Research 使用的统一 Access Token。

    对齐 IDENTITY_AND_ACCESS.md §3.1：Claims 只携带稳定身份语义，
    不携带 username 等可派生展示字段。
    """
    platform_user_id = str(uuid.UUID(str(user_id)))
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "iss": settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
        "aud": settings.platform_jwt_audiences,
        "sub": platform_user_id,
        "role": role,
        "token_type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT，失败时返回空 dict"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.EVIDSIGHT_KNOWLEDGE_JWT_AUDIENCE,
            issuer=settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
            options={
                "require_iss": True,
                "require_aud": True,
                "require_sub": True,
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
            },
        )
        uuid.UUID(payload["sub"])
        if payload.get("token_type") != "access" or not payload.get("jti"):
            return {}
        return payload
    except (JWTError, KeyError, TypeError, ValueError):
        return {}


def create_refresh_token(platform_user_id: str, family_id: str) -> str:
    """签发携带 Platform User 与 Token Family 身份的 Refresh Token。

    对齐 ARCHITECTURE.md §9.2.2：refresh_token 使用独立 JWT 签发，
    payload 中 type='refresh' 与 access_token 区分，防止混用。
    jti（JWT ID）确保每次生成的 token 唯一，避免同一秒内 token 碰撞。
    """
    subject = str(uuid.UUID(str(platform_user_id)))
    token_family_id = str(uuid.UUID(str(family_id)))
    secret = settings.REFRESH_TOKEN_SECRET_KEY or settings.JWT_SECRET_KEY
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "type": "refresh",
        "family_id": token_family_id,
        "jti": uuid.uuid4().hex,
        "exp": expire,
    }
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def decode_refresh_token(token: str) -> dict:
    """解码并验证 refresh_token，校验 type='refresh'。

    失败时抛出 JWTError（由调用方捕获处理）。
    """
    secret = settings.REFRESH_TOKEN_SECRET_KEY or settings.JWT_SECRET_KEY
    payload = jwt.decode(
        token,
        secret,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != "refresh":
        raise JWTError("token type is not refresh")
    try:
        payload["sub"] = str(uuid.UUID(payload["sub"]))
        payload["family_id"] = str(uuid.UUID(payload["family_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise JWTError("invalid refresh token identity") from exc
    return payload


def hash_token(token: str) -> str:
    """SHA-256 哈希 token，存入 MySQL（不存明文，对齐 DATABASE.md §2.7）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
