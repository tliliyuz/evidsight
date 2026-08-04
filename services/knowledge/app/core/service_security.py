"""Service JWT 验证 — Research 私钥签发，Knowledge 公钥验证（RS256）。

对齐 CONFIGURATION.md §3：Service Token 使用独立非对称密钥，与用户 Access Token
（HS256）完全隔离。验证失败一律返回空 dict，不抛出细节，由调用方构造契约错误信封。
"""

import json
from pathlib import Path

from jose import JWTError, jwt

from app.config import settings


def _load_public_keys() -> dict[str, str]:
    """读取公钥集文件：JSON 映射 {"<kid>": "<PEM>"}。"""
    path = Path(settings.EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_service_token(token: str) -> dict:
    """验证 Service JWT，成功返回 payload dict，失败返回 {}。

    校验顺序：签名（RS256）→ Key ID → Issuer → Audience → token_type → 时间窗口。
    """
    if not token:
        return {}
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        public_keys = _load_public_keys()
        if not kid or kid not in public_keys:
            return {}
        payload = jwt.decode(
            token,
            public_keys[kid],
            algorithms=[settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ALGORITHM],
            audience=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE,
            issuer=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER,
            options={
                "require_iss": True,
                "require_aud": True,
                "require_sub": True,
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
            },
        )
        if payload.get("token_type") != "service":
            return {}
        if not isinstance(payload.get("sub"), str) or not payload.get("sub"):
            return {}
        return payload
    except (JWTError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return {}
