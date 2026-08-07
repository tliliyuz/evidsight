"""Identity Status Provider 客户端 — Research 创建长期任务前实时复核用户状态。

对齐 API.md §11.1 与 TESTING.md IA-012 身份状态契约：
- 创建任务前调用 `GET /internal/v1/identity/users/{platform_user_id}/status`，不缓存用户状态；
- 请求必须携带 Service JWT、Contract 版本、X-Request-ID、W3C traceparent；
- 200 → 用户 active，放行；
- 403 AUTH_USER_DISABLED → 抛 UserDisabledException（E1010/401），失败关闭；
- 503 INTERNAL_IDENTITY_UNAVAILABLE、网络错误、超时或意外响应 → 抛 ServiceUnavailableException（E9002/503），失败关闭；
- 绝不用旧的 active 结果放行新任务。
"""

import logging
import uuid

import httpx

from app.config import settings
from app.core.exceptions import ServiceUnavailableException, UserDisabledException
from app.core.logging_config import request_id_var
from app.core.service_security import create_service_token

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1.0.0"


def _new_traceparent() -> str:
    """生成 W3C traceparent（version-00, flags=01）。"""
    trace_id = uuid.uuid4().hex  # 32 hex
    span_id = uuid.uuid4().hex[:16]  # 16 hex
    return f"00-{trace_id}-{span_id}-01"


async def check_user_status(platform_user_id: str) -> None:
    """创建任务前实时复核用户状态。失败关闭：禁用/不可用/网络异常均抛异常。

    :param platform_user_id: Platform User UUID（跨服务唯一用户标识）
    :raises UserDisabledException: 用户不存在或已禁用（403 AUTH_USER_DISABLED）
    :raises ServiceUnavailableException: 身份库不可用、网络错误、超时或意外响应
    """
    base_url = settings.EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL.rstrip("/")
    timeout = settings.EVIDSIGHT_IDENTITY_STATUS_TIMEOUT_SECONDS
    service_token = create_service_token()

    # X-Request-ID：优先透传当前调用链的 request_id，否则生成新 ID
    request_id = request_id_var.get() or uuid.uuid4().hex[:12]

    headers = {
        "Authorization": f"Bearer {service_token}",
        "X-EvidSight-Contract-Version": CONTRACT_VERSION,
        "X-Request-ID": request_id,
        "traceparent": _new_traceparent(),
    }
    url = f"{base_url}/internal/v1/identity/users/{platform_user_id}/status"

    logger.info(
        "复核用户状态: platform_user_id=%s, url=%s, request_id=%s",
        platform_user_id,
        url,
        request_id,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("身份事实源不可用: platform_user_id=%s, err=%s", platform_user_id, exc)
        raise ServiceUnavailableException("身份事实源暂时不可用，请稍后重试") from exc

    if response.status_code == 200:
        logger.info("用户状态复核通过: platform_user_id=%s", platform_user_id)
        return

    if response.status_code == 403:
        logger.warning("用户被禁用或不存在: platform_user_id=%s", platform_user_id)
        raise UserDisabledException()

    logger.warning(
        "身份状态校验返回异常状态码: status=%s, body=%s",
        response.status_code,
        response.text[:200],
    )
    raise ServiceUnavailableException("身份状态校验失败，请稍后重试")
