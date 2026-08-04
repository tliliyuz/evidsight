"""内部 API 路由器 — 服务间契约端点（仅 Service JWT 保护，不走用户 Bearer 中间件）。

对齐 API.md §11.1：校验顺序固定为 Research 服务身份 → Contract 版本和请求元数据
→ 用户状态。错误一律返回 error-response.schema.json 信封，与外部 API 扁平错误分离。
"""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.service_security import verify_service_token
from app.core.uuid_helpers import validate_uuid_format
from app.dependencies import get_db
from app.models.user import User

router = APIRouter(prefix="/internal/v1", tags=["internal"])

CONTRACT_VERSION = "1.0.0"


def _error_response(status_code: int, error_code: str, message: str,
                    request_id: str, retryable: bool) -> JSONResponse:
    """构造符合 error-response.schema.json 的契约错误信封。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "error_code": error_code,
                "message": message,
                "request_id": request_id,
                "retryable": retryable,
                "details": {},
            }
        },
    )


@router.get("/identity/users/{platform_user_id}/status")
async def identity_status(
    request: Request,
    platform_user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """返回用户权威状态。只有 active 用户产生 200；禁用/不存在返回 AUTH_USER_DISABLED。"""
    request_id = request.headers.get("X-Request-ID", "")

    # 1. Research 服务身份
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not verify_service_token(auth_header[7:]):
        return _error_response(401, "INTERNAL_SERVICE_UNAUTHENTICATED",
                               "服务身份无效或缺失", request_id, False)

    # 2. Contract 版本
    if request.headers.get("X-EvidSight-Contract-Version") != CONTRACT_VERSION:
        return _error_response(400, "INTERNAL_CONTRACT_UNSUPPORTED",
                               f"不支持的 Contract 版本，仅支持 {CONTRACT_VERSION}",
                               request_id, False)

    # 3. 请求关联元数据
    if not request_id or not request.headers.get("traceparent"):
        return _error_response(400, "INTERNAL_CONTRACT_INVALID",
                               "缺少 X-Request-ID 或 traceparent", request_id, False)

    # 4. Platform User UUID
    if not validate_uuid_format(platform_user_id):
        return _error_response(400, "INTERNAL_CONTRACT_INVALID",
                               "platform_user_id 不是合法 UUID", request_id, False)

    # 5. 用户状态
    try:
        result = await db.execute(
            select(User).where(User.platform_user_id == platform_user_id)
        )
        user = result.scalar_one_or_none()
    except Exception:
        return _error_response(503, "INTERNAL_IDENTITY_UNAVAILABLE",
                               "身份数据库暂时不可用", request_id, True)

    if user is None or user.status != "active":
        return _error_response(403, "AUTH_USER_DISABLED",
                               "用户不存在或已被禁用", request_id, False)

    return JSONResponse(
        status_code=200,
        content={
            "contract_version": CONTRACT_VERSION,
            "platform_user_id": platform_user_id,
            "status": "active",
            "status_version": user.status_version or 0,
        },
    )
