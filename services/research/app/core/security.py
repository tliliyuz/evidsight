"""Research Access Token 验证。

Research 不拥有用户凭证，不签发 Access/Refresh Token；统一身份由 Knowledge
身份模块签发，Research 只验证面向自身 Audience 的 Access Token。
"""

import uuid

from jose import JWTError, jwt

from app.config import settings


def decode_access_token(token: str, ignore_expired: bool = False) -> dict:
    """验证统一 Access Token，失败时返回空字典。

    ignore_expired=True 时跳过 exp 校验（仅用于区分「已过期」与「无效」），
    其余 Claim 校验（签名/算法/Issuer/Audience/type/jti/sub）保持不变。
    """
    options = {
        "require_iss": True,
        "require_aud": True,
        "require_sub": True,
        "require_exp": not ignore_expired,
        "require_iat": True,
        "require_nbf": True,
    }
    if ignore_expired:
        options["verify_exp"] = False
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.EVIDSIGHT_RESEARCH_JWT_AUDIENCE,
            issuer=settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
            options=options,
        )
        uuid.UUID(payload["sub"])
        if payload.get("token_type") != "access" or not payload.get("jti"):
            return {}
        return payload
    except (JWTError, KeyError, TypeError, ValueError):
        return {}


def decode_access_token_with_status(token: str) -> tuple[dict, str]:
    """验证统一 Access Token 并区分失败原因。

    返回 (payload, status)，status ∈ {"ok", "expired", "invalid"}：
    - "ok"：全部校验通过，payload 为有效载荷；
    - "expired"：其余校验全部通过、仅 exp 已过，对齐 E1003 AUTH_TOKEN_EXPIRED；
    - "invalid"：签名失败、Claim 缺失或类型错误等其他原因，对齐 E1004 AUTH_TOKEN_INVALID。

    AuthMiddleware 据此向客户端区分：前端只在收到 AUTH_TOKEN_EXPIRED 时静默刷新，
    其余 401 视为不可恢复的认证失败（此前把过期统一归为 E1004，导致前端把
    过期当致命错误直接登出，见 CHANGELOG 2026-08-12）。
    """
    payload = decode_access_token(token)
    if payload:
        return payload, "ok"
    if decode_access_token(token, ignore_expired=True):
        return {}, "expired"
    return {}, "invalid"
