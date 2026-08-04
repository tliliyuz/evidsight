"""内部 API 路由器 — 服务间契约端点（仅 Service JWT 保护，不走用户 Bearer 中间件）。

对齐 API.md §11.1：校验顺序固定为 Research 服务身份 → Contract 版本和请求元数据
→ 用户状态。错误一律返回 error-response.schema.json 信封，与外部 API 扁平错误分离。
"""

import json
import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.service_security import verify_service_token
from app.core.uuid_helpers import validate_uuid_format
from app.dependencies import get_db
from app.models.user import User
from app.services import internal_retrieval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])

CONTRACT_VERSION = "1.0.0"

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$")
_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

_SEARCH_ALLOWED_KEYS = {
    "contract_version", "user_id", "knowledge_base_ids", "query", "purpose",
    "limit", "filters",
}
_FILTER_ALLOWED_KEYS = {"document_ids", "languages", "updated_since", "updated_until"}
_REF_ALLOWED_KEYS = {
    "knowledge_base_id", "document_id", "document_version_id", "segment_id",
}
_RESOLVE_ALLOWED_KEYS = {"contract_version", "user_id", "references", "purpose"}


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


def _check_service_request(request: Request) -> tuple[str, JSONResponse | None]:
    """服务身份 → Contract 版本 → 关联元数据校验。返回 (request_id, error 或 None)。

    对齐 contracts/README.md §3 的固定处理顺序，供 Retrieval/Resolve 端点复用。
    """
    request_id = request.headers.get("X-Request-ID", "")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not verify_service_token(auth_header[7:]):
        return request_id, _error_response(
            401, "INTERNAL_SERVICE_UNAUTHENTICATED", "服务身份无效或缺失",
            request_id, False)

    if request.headers.get("X-EvidSight-Contract-Version") != CONTRACT_VERSION:
        return request_id, _error_response(
            400, "INTERNAL_CONTRACT_UNSUPPORTED",
            f"不支持的 Contract 版本，仅支持 {CONTRACT_VERSION}",
            request_id, False)

    if not request_id or not request.headers.get("traceparent"):
        return request_id, _error_response(
            400, "INTERNAL_CONTRACT_INVALID",
            "缺少 X-Request-ID 或 traceparent", request_id, False)

    return request_id, None


def _validate_search_payload(body) -> str | None:
    """检索请求体结构校验（对齐 retrieval-request.schema.json）。非法返回错误消息。"""
    if not isinstance(body, dict):
        return "请求体必须是 JSON 对象"
    unknown = set(body) - _SEARCH_ALLOWED_KEYS
    if unknown:
        return f"包含未知字段: {sorted(unknown)}"
    missing = [k for k in ("contract_version", "user_id", "knowledge_base_ids", "query", "purpose")
               if k not in body]
    if missing:
        return f"缺少必填字段: {sorted(missing)}"
    if not isinstance(body["contract_version"], str) or not _SEMVER_PATTERN.match(body["contract_version"]):
        return "contract_version 不是合法 SemVer"
    if not validate_uuid_format(body["user_id"]):
        return "user_id 不是合法 UUID"
    kb_ids = body["knowledge_base_ids"]
    if not isinstance(kb_ids, list) or not (1 <= len(kb_ids) <= 50):
        return "knowledge_base_ids 必须是 1-50 个元素的数组"
    if len(set(kb_ids)) != len(kb_ids):
        return "knowledge_base_ids 不能重复"
    if any(not isinstance(x, str) or not validate_uuid_format(x) for x in kb_ids):
        return "knowledge_base_ids 中存在非法 UUID"
    if not isinstance(body["query"], str):
        return "query 必须是字符串"
    if body["purpose"] != "research_retrieval":
        return "purpose 只支持 research_retrieval"
    limit = body.get("limit")
    if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 100)):
        return "limit 必须是 1-100 的整数"
    if "filters" in body:
        return _validate_filters(body["filters"])
    return None


def _validate_filters(filters) -> str | None:
    """检索过滤器结构校验（对齐 retrieval-request.schema.json $defs.RetrievalFilters）。"""
    if not isinstance(filters, dict):
        return "filters 必须是 JSON 对象"
    unknown = set(filters) - _FILTER_ALLOWED_KEYS
    if unknown:
        return f"filters 包含未知字段: {sorted(unknown)}"
    document_ids = filters.get("document_ids")
    if document_ids is not None:
        if not isinstance(document_ids, list) or not (1 <= len(document_ids) <= 100):
            return "filters.document_ids 必须是 1-100 个元素的数组"
        if len(set(document_ids)) != len(document_ids):
            return "filters.document_ids 不能重复"
        if any(not isinstance(x, str) or not validate_uuid_format(x) for x in document_ids):
            return "filters.document_ids 中存在非法 UUID"
    languages = filters.get("languages")
    if languages is not None:
        if not isinstance(languages, list) or not (1 <= len(languages) <= 20):
            return "filters.languages 必须是 1-20 个元素的数组"
        if len(set(languages)) != len(languages):
            return "filters.languages 不能重复"
        if any(not isinstance(x, str) or not x for x in languages):
            return "filters.languages 中存在空字符串"
    for key in ("updated_since", "updated_until"):
        value = filters.get(key)
        if value is not None and (
                not isinstance(value, str) or not _TIMESTAMP_PATTERN.match(value)):
            return f"filters.{key} 不是合法 RFC3339 UTC 时间"
    if ("updated_since" in filters and "updated_until" in filters
            and filters["updated_since"] > filters["updated_until"]):
        return "filters.updated_since 必须早于或等于 updated_until"
    return None


def _validate_resolve_payload(body) -> str | None:
    """解析请求体结构校验（对齐 evidence-resolve-request.schema.json）。非法返回错误消息。"""
    if not isinstance(body, dict):
        return "请求体必须是 JSON 对象"
    unknown = set(body) - _RESOLVE_ALLOWED_KEYS
    if unknown:
        return f"包含未知字段: {sorted(unknown)}"
    missing = [k for k in ("contract_version", "user_id", "references", "purpose") if k not in body]
    if missing:
        return f"缺少必填字段: {sorted(missing)}"
    if not isinstance(body["contract_version"], str) or not _SEMVER_PATTERN.match(body["contract_version"]):
        return "contract_version 不是合法 SemVer"
    if not validate_uuid_format(body["user_id"]):
        return "user_id 不是合法 UUID"
    refs = body["references"]
    if not isinstance(refs, list) or not (1 <= len(refs) <= 100):
        return "references 必须是 1-100 个元素的数组"
    seen: set[tuple] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            return "references 元素必须是 JSON 对象"
        if set(ref) != _REF_ALLOWED_KEYS:
            return "references 元素字段不合法（只允许 knowledge_base_id/document_id/document_version_id/segment_id）"
        for key in _REF_ALLOWED_KEYS:
            if not isinstance(ref[key], str) or not validate_uuid_format(ref[key]):
                return f"references 元素 {key} 不是合法 UUID"
        identity = tuple(ref[k] for k in _REF_ALLOWED_KEYS)
        if identity in seen:
            return "references 存在重复引用"
        seen.add(identity)
    if body["purpose"] != "research_evidence_resolve":
        return "purpose 只支持 research_evidence_resolve"
    return None


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


@router.post("/retrieval/search")
async def retrieval_search(request: Request, db: AsyncSession = Depends(get_db)):
    """权限感知检索：服务身份 → 版本与结构 → 用户 active → 逐 KB READ → 检索。

    对齐 API.md §11.2 / contracts/README.md §3；响应为 retrieval-response.schema.json。
    """
    request_id, error = _check_service_request(request)
    if error is not None:
        return error

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(400, "INTERNAL_CONTRACT_INVALID",
                               "请求体不是合法 JSON", request_id, False)

    invalid = _validate_search_payload(body)
    if invalid:
        return _error_response(400, "INTERNAL_CONTRACT_INVALID", invalid, request_id, False)

    try:
        response = await internal_retrieval.search_internal(db, body, request_id)
    except internal_retrieval.InternalRetrievalError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message,
                               request_id, exc.retryable)
    except Exception:
        logger.exception("Internal Retrieval 未知错误")
        return _error_response(503, "INTERNAL_RETRIEVAL_UNAVAILABLE",
                               "检索服务暂时不可用", request_id, True)
    return JSONResponse(status_code=200, content=response)


@router.post("/retrieval/resolve")
async def retrieval_resolve(request: Request, db: AsyncSession = Depends(get_db)):
    """Evidence 引用解析：先全部 KB READ 校验，再逐引用解析稳定身份（整批原子）。

    对齐 API.md §11.2 / contracts/README.md §3；响应为 evidence-resolve-response.schema.json。
    """
    request_id, error = _check_service_request(request)
    if error is not None:
        return error

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(400, "INTERNAL_CONTRACT_INVALID",
                               "请求体不是合法 JSON", request_id, False)

    invalid = _validate_resolve_payload(body)
    if invalid:
        return _error_response(400, "INTERNAL_CONTRACT_INVALID", invalid, request_id, False)

    try:
        response = await internal_retrieval.resolve_internal(db, body, request_id)
    except internal_retrieval.InternalRetrievalError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message,
                               request_id, exc.retryable)
    except Exception:
        logger.exception("Internal Resolve 未知错误")
        return _error_response(503, "INTERNAL_RETRIEVAL_UNAVAILABLE",
                               "解析服务暂时不可用", request_id, True)
    return JSONResponse(status_code=200, content=response)
