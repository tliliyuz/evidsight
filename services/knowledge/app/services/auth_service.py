"""认证业务逻辑 — 注册 / 登录 / Token 刷新 / 退出 / 改密。

身份与轮换语义以 IDENTITY_AND_ACCESS.md 为准。
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    InvalidCredentialsException,
    InvalidRefreshTokenException,
    PasswordSameAsCurrentException,
    RefreshTokenExpiredException,
    RefreshTokenRevokedException,
    TokenLeakDetectedException,
    UserDisabledException,
    UsernameExistsException,
)
from app.core.logging_config import get_request_id
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.identity_audit_event import IdentityAuditEvent
from app.models.refresh_token import RefreshToken
from app.models.refresh_token_family import RefreshTokenFamily
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse, UserSummary

logger = logging.getLogger(__name__)


def _platform_user_id(user: User) -> str:
    """读取或生成过渡期 Platform User UUID。"""
    if not user.platform_user_id:
        user.platform_user_id = str(uuid.uuid4())
    return user.platform_user_id


async def _create_user(db: AsyncSession, username: str, password: str) -> User:
    """创建新用户并刷新，返回 ORM 实例。用户名重复时抛出 UsernameExistsException。"""
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none() is not None:
        raise UsernameExistsException(username)

    user = User(
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def register(db: AsyncSession, username: str, password: str) -> UserResponse:
    """注册新用户（旧 /api/auth/register 兼容入口），返回旧 UserResponse（id 为内部 users.id）。"""
    user = await _create_user(db, username, password)
    return UserResponse.model_validate(user)


async def register_v1(db: AsyncSession, username: str, password: str) -> UserSummary:
    """注册新用户（对齐 IA-017），返回 UserSummary，id 为 Platform User UUID。

    不含 Knowledge 内部 users.id；与 /api/v1/auth/me 的 UserSummary 形状一致。
    """
    user = await _create_user(db, username, password)
    return UserSummary(
        id=uuid.UUID(_platform_user_id(user)),
        username=user.username,
        role=user.role,
        status=user.status,
    )


async def get_current_user_profile(
    db: AsyncSession, platform_user_id: str
) -> UserSummary:
    """返回当前用户的外部身份摘要，字段取自数据库当前状态。

    对齐 API.md §5 GET /api/v1/auth/me：
    - id 为 Platform User UUID（users.platform_user_id）；
    - username / role / status 均从数据库当前状态读取，不拼装 Token Claim。
    用户不存在或已禁用统一返回 401 E5010（与身份规范「不区分」原则一致）。
    """
    result = await db.execute(select(User).where(User.platform_user_id == platform_user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status == "disabled":
        raise UserDisabledException()
    return UserSummary(
        id=uuid.UUID(user.platform_user_id),
        username=user.username,
        role=user.role,
        status=user.status,
    )


async def login(db: AsyncSession, username: str, password: str) -> TokenResponse:
    """验证用户名密码，返回 access_token + refresh_token。

    对齐 API.md §2 POST /api/auth/login：
    - access_token 15min 短有效期
    - refresh_token 7 天长有效期，SHA-256 哈希存 MySQL
    """
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsException()

    # 禁用用户拒绝登录
    if user.status == "disabled":
        raise UserDisabledException()

    # 签发 token 对
    access_token = create_access_token(_platform_user_id(user), user.role)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    family = RefreshTokenFamily(
        id=str(uuid.uuid4()),
        user_id=_platform_user_id(user),
        expires_at=expires_at,
    )
    db.add(family)
    refresh_token_str = create_refresh_token(user.platform_user_id, family.id)

    # refresh_token 哈希存 MySQL
    rt = RefreshToken(
        family_id=family.id,
        token_hash=hash_token(refresh_token_str),
        issued_at=now,
        expires_at=expires_at,
    )
    db.add(rt)
    await db.flush()

    logger.info("用户登录成功: user_id=%d", user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def refresh(db: AsyncSession, refresh_token_str: str) -> TokenResponse:
    """锁定旧 Refresh Token，并在当前请求事务中建立唯一后继。"""
    # 1. 解码 JWT
    try:
        payload = decode_refresh_token(refresh_token_str)
        platform_user_id = str(uuid.UUID(payload["sub"]))
        family_id = str(uuid.UUID(payload["family_id"]))
    except JWTError:
        raise InvalidRefreshTokenException("refresh_token 解码失败或已过期")
    except (KeyError, ValueError, TypeError):
        raise InvalidRefreshTokenException("refresh_token 载荷字段缺失或格式错误")

    # 2. SHA-256 哈希 → 查表
    token_hash = hash_token(refresh_token_str)
    result = await db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.family_id == family_id,
        )
        .with_for_update()
    )
    rt = result.scalar_one_or_none()

    if rt is None:
        # token 不在数据库中（可能从未存储或已被清理）
        raise InvalidRefreshTokenException("refresh_token 不存在")

    # 已轮换 Token 再次出现属于重放，安全状态必须在返回 401 前持久化。
    if rt.rotated_at is not None:
        family_result = await db.execute(
            select(RefreshTokenFamily)
            .where(RefreshTokenFamily.id == family_id)
            .with_for_update()
        )
        replayed_family = family_result.scalar_one_or_none()
        if replayed_family is not None:
            now = datetime.now(timezone.utc)
            if replayed_family.revoked_at is None:
                replayed_family.revoked_at = now
                replayed_family.revoke_reason = "refresh_token_replay"
            db.add(
                IdentityAuditEvent(
                    user_id=replayed_family.user_id,
                    actor_user_id=None,
                    event_type="refresh_replay",
                    request_id=get_request_id() or None,
                    outcome="denied",
                    details={
                        "family_id": replayed_family.id,
                        "action": "family_revoked",
                    },
                )
            )
            await db.flush()
            await db.commit()
        raise TokenLeakDetectedException()

    if rt.revoked_at is not None:
        raise RefreshTokenRevokedException()

    # 检查过期（DB 已存储 UTC，ORM DateTime(timezone=True) 返回 aware datetime）
    if rt.expires_at < datetime.now(timezone.utc):
        raise RefreshTokenExpiredException()

    family = await db.get(RefreshTokenFamily, family_id)
    now = datetime.now(timezone.utc)
    if family is None or family.revoked_at is not None or family.expires_at < now:
        raise RefreshTokenRevokedException()

    result = await db.execute(
        select(User).where(User.platform_user_id == platform_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidRefreshTokenException("用户不存在")

    # 禁用用户拒绝刷新
    if user.status == "disabled":
        raise UserDisabledException()

    new_access_token = create_access_token(platform_user_id, user.role)
    new_refresh_token_str = create_refresh_token(platform_user_id, family_id)

    new_rt = RefreshToken(
        family_id=family_id,
        token_hash=hash_token(new_refresh_token_str),
        issued_at=now,
        expires_at=min(family.expires_at, now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)),
    )
    db.add(new_rt)
    rt.rotated_at = now
    rt.replaced_by = new_rt
    family.last_rotated_at = now
    await db.flush()

    logger.info("Token 刷新成功: platform_user_id=%s", platform_user_id)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def logout(db: AsyncSession, refresh_token_str: str, platform_user_id: str) -> None:
    """吊销属于当前 Platform User 的 Refresh Token Family。"""
    try:
        payload = decode_refresh_token(refresh_token_str)
    except JWTError:
        raise InvalidRefreshTokenException("refresh_token 解码失败")

    if payload["sub"] != platform_user_id:
        return

    token_hash = hash_token(refresh_token_str)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.family_id == payload["family_id"],
        )
    )
    rt = result.scalar_one_or_none()

    family = await db.get(RefreshTokenFamily, payload["family_id"])
    if rt is not None and family is not None and family.revoked_at is None:
        now = datetime.now(timezone.utc)
        family.revoked_at = now
        family.revoke_reason = "logout"
        rt.revoked_at = now
        await db.flush()
        logger.info("refresh_token family 已吊销: platform_user_id=%s", platform_user_id)


async def change_password(
    db: AsyncSession, user_id: int, old_password: str, new_password: str
) -> None:
    """修改密码 + 吊销该用户全部 refresh_token（强制下线）。

    对齐 API.md §2 PUT /api/auth/password。
    新密码不能与当前密码相同。
    """
    user = await db.get(User, user_id)
    if user is None:
        raise InvalidCredentialsException()

    if not verify_password(old_password, user.password_hash):
        raise InvalidCredentialsException()

    if old_password == new_password:
        raise PasswordSameAsCurrentException()

    # 更新密码
    user.password_hash = hash_password(new_password)
    await db.flush()

    # 吊销该用户全部 refresh_token
    await revoke_all_user_tokens(db, _platform_user_id(user))

    logger.info("密码修改成功，全部 refresh_token 已吊销: user_id=%d", user_id)


async def revoke_all_user_tokens(db: AsyncSession, platform_user_id: str) -> None:
    """吊销指定 Platform User 的全部有效 Refresh Token Family。"""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(RefreshTokenFamily)
        .where(
            RefreshTokenFamily.user_id == platform_user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoke_reason="user_security_change")
    )
    await db.flush()
