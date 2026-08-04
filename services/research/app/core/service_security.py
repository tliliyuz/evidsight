"""Service JWT 签发 — Research 用私钥为服务身份签名（RS256）。

对齐 CONFIGURATION.md §3：Service Token 使用独立非对称密钥，与用户 Access Token
（HS256）完全隔离。签发结果供 Research 访问 Knowledge 内部端点前使用。
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import jwt

from app.config import settings


def create_service_token() -> str:
    """签发 Service JWT，返回带 Key ID 与短 TTL 的 RS256 Token。"""
    private_pem = Path(settings.EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE).read_text(
        encoding="utf-8"
    )
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS)
    payload = {
        "iss": settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER,
        "aud": settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE,
        "sub": "research-service",
        "token_type": "service",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        private_pem,
        algorithm=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ALGORITHM,
        headers={"kid": settings.EVIDSIGHT_RESEARCH_SERVICE_JWT_ACTIVE_KID},
    )
