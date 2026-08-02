"""Research Access Token 验证。

Research 不拥有用户凭证，不签发 Access/Refresh Token；统一身份由 Knowledge
身份模块签发，Research 只验证面向自身 Audience 的 Access Token。
"""

import uuid

from jose import JWTError, jwt

from app.config import settings


def decode_access_token(token: str) -> dict:
    """验证统一 Access Token，失败时返回空字典。"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.EVIDSIGHT_RESEARCH_JWT_AUDIENCE,
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
