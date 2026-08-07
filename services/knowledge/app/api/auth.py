"""认证接口 — 注册 / 登录 / Token 刷新 / 退出 / 改密

对齐 API.md §2 / §5：
- POST /api/auth/register — 注册
- POST /api/auth/login — 登录（返回 access_token + refresh_token）
- POST /api/auth/refresh — Token 刷新（Rotation）
- POST /api/auth/logout — 吊销 refresh_token
- PUT /api/auth/password — 改密 + 吊销全部 refresh_token
- v1 系列（Cookie + CSRF）见 ADR-006，body refresh_token 为迁移期兼容入口（IA-016）
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.csrf import (
    clear_auth_cookies,
    generate_csrf_token,
    set_csrf_cookie,
    set_refresh_cookie,
    verify_csrf,
)
from app.core.exceptions import AppException, InvalidRefreshTokenException
from app.dependencies import get_db, get_current_user
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginV1Response,
    LogoutRequest,
    RefreshRequest,
    RefreshV1Response,
    RegisterRequest,
    UserSummary,
)
from app.services.auth_service import (
    change_password,
    get_current_user_profile,
    login,
    login_v1,
    logout,
    refresh,
    register,
    register_v1,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
v1_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

logger = logging.getLogger(__name__)


@v1_router.get("/me", response_model=UserSummary)
async def me(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户外部身份摘要（对齐 API.md §5 GET /api/v1/auth/me）。"""
    return await get_current_user_profile(db, user["platform_user_id"])


@v1_router.post("/register", status_code=201, response_model=UserSummary)
async def register_user_v1(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册新用户（对齐 IA-017，返回 UserSummary，id 为 Platform User UUID）。

    旧 POST /api/auth/register 保留为迁移期兼容入口（返回 id=int 的 UserResponse）。
    """
    return await register_v1(db, req.username, req.password)


@v1_router.post("/login", response_model=LoginV1Response)
async def login_user_v1(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """登录（对齐 ADR-006 / API.md §5 POST /api/v1/auth/login）。

    Refresh Token 通过 HttpOnly Cookie 下发，响应体不含 refresh_token 明文；
    同时设置非 HttpOnly 的 CSRF Cookie（double-submit 模式），供刷新/退出请求回传。
    """
    access_token, refresh_token_str, user = await login_v1(db, req.username, req.password)
    set_refresh_cookie(response, refresh_token_str)
    set_csrf_cookie(response, generate_csrf_token())
    return LoginV1Response(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@v1_router.post("/refresh", response_model=RefreshV1Response)
async def refresh_token_v1(
    request: Request,
    response: Response,
    req: RefreshRequest | None = None,
    _: None = Depends(verify_csrf),
    db: AsyncSession = Depends(get_db),
):
    """刷新（对齐 ADR-006 / API.md §5 POST /api/v1/auth/refresh）。

    verify_csrf 依赖先于任何 Refresh Token 解码/轮换执行：CSRF 失败返回 E5004，
    绝不进入轮换、撤销或重放审计分支（ADR-006）。
    从 HttpOnly Refresh Cookie 读取 Token，成功后在同一响应轮换 Refresh/CSRF Cookie；
    重放检测、Family 撤销、用户禁用、过期等刷新失败必须清除 Cookie。
    """
    refresh_token_str = request.cookies.get(settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME)
    if not refresh_token_str:
        # 迁移期兼容入口（IA-016）：配置开启且 Cookie 缺失时回退读取 body
        if (
            settings.EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT
            and req is not None
            and req.refresh_token
        ):
            logger.warning(
                "弃用: Refresh Cookie 缺失，回退读取 body refresh_token（迁移期兼容，观测归零后删除）"
            )
            refresh_token_str = req.refresh_token
        else:
            raise InvalidRefreshTokenException("缺少 Refresh Cookie")
    try:
        token = await refresh(db, refresh_token_str)
    except AppException as exc:
        # 刷新失败：标记清除 Cookie，由全局 AppException handler 在错误响应上执行
        # （注入的 Response 在抛异常时会被错误响应替换，Cookie 必须挂在错误响应上）。
        exc.clear_auth_cookies = True
        raise
    set_refresh_cookie(response, token.refresh_token)
    set_csrf_cookie(response, generate_csrf_token())
    return RefreshV1Response(
        access_token=token.access_token,
        expires_in=token.expires_in,
    )


@v1_router.post("/logout", status_code=204)
async def logout_user_v1(
    request: Request,
    response: Response,
    req: LogoutRequest | None = None,
    _: None = Depends(verify_csrf),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """退出（对齐 ADR-006 / API.md §5 POST /api/v1/auth/logout）。

    需要 Access Token + Refresh Cookie + CSRF。verify_csrf 先于任何 Token 处理执行；
    幂等撤销当前 Token Family 并清除 Refresh/CSRF Cookie，重复退出不泄露 Token 状态。
    logout 不加 _PUBLIC_PATHS：需要 Access Token，不走中间件公开豁免。
    """
    refresh_token_str = request.cookies.get(settings.EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME)
    if not refresh_token_str:
        # 迁移期兼容入口（IA-016）：配置开启且 Cookie 缺失时回退读取 body
        if (
            settings.EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT
            and req is not None
            and req.refresh_token
        ):
            logger.warning(
                "弃用: Refresh Cookie 缺失，回退读取 body refresh_token（迁移期兼容，观测归零后删除）"
            )
            refresh_token_str = req.refresh_token
    if refresh_token_str:
        await logout(db, refresh_token_str, user["platform_user_id"])
    clear_auth_cookies(response)
    response.status_code = 204
    return response


@router.post("/register", status_code=201, response_model=dict)
async def register_user(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await register(db, req.username, req.password)
    return {"code": "0", "message": "注册成功", "data": user.model_dump()}


@router.post("/login", response_model=dict)
async def login_user(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    token = await login(db, req.username, req.password)
    return {"code": "0", "message": "登录成功", "data": token.model_dump()}


@router.post("/refresh", response_model=dict)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token = await refresh(db, req.refresh_token)
    return {"code": "0", "message": "Token 刷新成功", "data": token.model_dump()}


@router.post("/logout", response_model=dict)
async def logout_user(
    req: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    await logout(db, req.refresh_token, user["platform_user_id"])
    return {"code": "0", "message": "已退出登录", "data": None}


@router.put("/password", response_model=dict)
async def change_user_password(
    req: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    await change_password(db, user["user_id"], req.old_password, req.new_password)
    return {"code": "0", "message": "密码修改成功，所有设备已下线", "data": None}
