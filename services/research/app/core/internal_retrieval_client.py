"""Internal Retrieval Consumer 客户端 — Research 通过 Contract 调用 Knowledge 内部检索。

对齐 contracts/README.md §6-7/§10、RESEARCH_PIPELINE.md §6.1 与 ADR-010：
- `search_retrieval()`：POST /internal/v1/retrieval/search，返回按契约校验的命中；
- `resolve_retrieval()`：POST /internal/v1/retrieval/resolve，按稳定身份精确重取当前可访问正文；
- 请求必须携带 Service JWT、X-EvidSight-Contract-Version、X-Request-ID、traceparent；
- 请求体只含契约字段，不得携带 role/owner/authorized 等调用方计算的授权结论；
- 错误映射：KB_FORBIDDEN → fail-closed（E3115）、AUTH_USER_DISABLED → E1010、
  INTERNAL_CONTRACT_UNSUPPORTED/INVALID → 契约错误（E3117，不重试）、
  INTERNAL_RETRIEVAL_UNAVAILABLE / 限流 / 网络 / 超时 → 可重试（E3116）；
- 响应严格校验：returned_count == len(results)、命中必须含完整稳定身份；
- minimal_excerpt 只存在于返回对象内存中，本模块不持久化任何正文。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.core.exceptions import (
    InternalKnowledgeForbiddenException,
    InternalRetrievalContractException,
    InternalRetrievalUnavailableException,
    UserDisabledException,
)
from app.core.logging_config import request_id_var
from app.core.service_security import create_service_token

logger = logging.getLogger(__name__)

RETRIEVAL_CONTRACT_VERSION = "1.0.0"

# 命中必须包含的稳定身份字段（contracts/README.md §7.1）
_REQUIRED_HIT_IDENTITY_FIELDS = (
    "hit_id",
    "knowledge_base_id",
    "document_id",
    "document_version_id",
    "segment_id",
)

# 可重试的 Provider 错误码（contracts/README.md §10）
_RETRYABLE_ERROR_CODES = {
    "INTERNAL_RETRIEVAL_UNAVAILABLE",
    "INTERNAL_RATE_LIMITED",
    "INTERNAL_IDENTITY_UNAVAILABLE",
}

# 契约错误码：fail-closed，不重试
_CONTRACT_ERROR_CODES = {
    "INTERNAL_CONTRACT_UNSUPPORTED",
    "INTERNAL_CONTRACT_INVALID",
    "INTERNAL_SERVICE_UNAUTHENTICATED",
    "EVIDENCE_SOURCE_UNAVAILABLE",
}

# 指数退避基础延迟（秒）
_RETRY_BASE_DELAY = 0.5


@dataclass
class RetrievalHit:
    """Internal Retrieval 返回的单条命中（仅当前 Step 内存使用，正文禁止持久化）。

    对齐 contracts/README.md §7.1 RetrievalHit。
    """

    hit_id: str
    knowledge_base_id: str
    document_id: str
    document_version_id: str
    segment_id: str
    document_display_name: str
    section_title: str | None = None
    location: dict = field(default_factory=dict)
    minimal_excerpt: str = ""
    scores: list[dict] = field(default_factory=list)
    source_updated_at: str = ""
    retrieved_at: str = ""
    access_scope: str = "internal"

    def to_safe_dict(self) -> dict[str, Any]:
        """转换为不含 minimal_excerpt 的安全摘要（供 Step 输出 / 持久化引用）。

        对齐 contracts/README.md §9：转换前删除摘录及任何等价正文。
        """
        return {
            "hit_id": self.hit_id,
            "knowledge_base_id": self.knowledge_base_id,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment_id": self.segment_id,
            "document_display_name": self.document_display_name,
            "section_title": self.section_title,
            "location": self.location,
            "scores": self.scores,
            "source_updated_at": self.source_updated_at,
            "retrieved_at": self.retrieved_at,
            "access_scope": self.access_scope,
        }


@dataclass
class RetrievalSearchResult:
    """按契约校验后的检索响应。"""

    contract_version: str
    request_id: str
    results: list[RetrievalHit]
    returned_count: int
    has_more: bool = False


@dataclass
class ResolvedReference:
    """按稳定身份精确重取的内部正文（仅当前 Step 内存使用）。"""

    source_identity: dict
    minimal_excerpt: str = ""
    location: dict = field(default_factory=dict)
    source_updated_at: str = ""


def _new_traceparent() -> str:
    """生成 W3C traceparent（version-00, flags=01）。"""
    trace_id = uuid.uuid4().hex  # 32 hex
    span_id = uuid.uuid4().hex[:16]  # 16 hex
    return f"00-{trace_id}-{span_id}-01"


def _request_headers() -> dict:
    """构造 Internal Retrieval 请求头（服务身份 + 契约版本 + 关联上下文）。"""
    service_token = create_service_token()
    request_id = request_id_var.get() or uuid.uuid4().hex[:12]
    return {
        "Authorization": f"Bearer {service_token}",
        "X-EvidSight-Contract-Version": RETRIEVAL_CONTRACT_VERSION,
        "X-Request-ID": request_id,
        "traceparent": _new_traceparent(),
        "Content-Type": "application/json",
    }


def _raise_contract_error(error_code: str, message: str) -> None:
    """将 Provider 契约/认证错误映射为 fail-closed 异常。

    KB_FORBIDDEN 单独映射（E3115）；其余契约错误统一 E3117，均不重试。
    """
    if error_code == "KB_FORBIDDEN":
        raise InternalKnowledgeForbiddenException(message)
    if error_code == "AUTH_USER_DISABLED":
        raise UserDisabledException()
    raise InternalRetrievalContractException(f"{error_code}: {message}")


def _validate_hit(hit: dict, index: int) -> None:
    """校验单个命中：必须包含完整稳定身份（contracts/README.md §7.1）。"""
    missing = [f for f in _REQUIRED_HIT_IDENTITY_FIELDS if not hit.get(f)]
    if missing:
        raise InternalRetrievalContractException(
            f"命中 {index} 缺少稳定身份字段: {', '.join(missing)}"
        )


def _parse_search_response(payload: dict) -> RetrievalSearchResult:
    """按契约校验并解析 retrieval-response。

    Returns:
        RetrievalSearchResult：已校验的命中列表（minimal_excerpt 仅在内存）
    """
    if not isinstance(payload, dict):
        raise InternalRetrievalContractException("检索响应不是 JSON 对象")

    results = payload.get("results")
    if not isinstance(results, list):
        raise InternalRetrievalContractException("检索响应缺少 results 数组")

    returned_count = payload.get("returned_count")
    if returned_count != len(results):
        raise InternalRetrievalContractException(
            f"returned_count={returned_count} 与 results 长度 {len(results)} 不一致"
        )

    hits: list[RetrievalHit] = []
    for i, hit in enumerate(results):
        if not isinstance(hit, dict):
            raise InternalRetrievalContractException(f"命中 {i} 不是对象")
        _validate_hit(hit, i)
        hits.append(
            RetrievalHit(
                hit_id=str(hit["hit_id"]),
                knowledge_base_id=str(hit["knowledge_base_id"]),
                document_id=str(hit["document_id"]),
                document_version_id=str(hit["document_version_id"]),
                segment_id=str(hit["segment_id"]),
                document_display_name=str(hit.get("document_display_name") or ""),
                section_title=hit.get("section_title"),
                location=hit.get("location") or {},
                minimal_excerpt=str(hit.get("minimal_excerpt") or ""),
                scores=hit.get("scores") or [],
                source_updated_at=str(hit.get("source_updated_at") or ""),
                retrieved_at=str(hit.get("retrieved_at") or ""),
                access_scope=str(hit.get("access_scope") or "internal"),
            )
        )

    return RetrievalSearchResult(
        contract_version=str(payload.get("contract_version") or ""),
        request_id=str(payload.get("request_id") or ""),
        results=hits,
        returned_count=int(returned_count or 0),
        has_more=bool(payload.get("has_more")),
    )


def _parse_resolve_response(payload: dict) -> list[ResolvedReference]:
    """按契约校验并解析 evidence-resolve-response。

    Returns:
        list[ResolvedReference]：按请求顺序的稳定身份与当前可访问正文
    """
    if not isinstance(payload, dict):
        raise InternalRetrievalContractException("解析响应不是 JSON 对象")

    resolved = payload.get("resolved")
    if not isinstance(resolved, list):
        raise InternalRetrievalContractException("解析响应缺少 resolved 数组")

    resolved_count = payload.get("resolved_count")
    if resolved_count != len(resolved):
        raise InternalRetrievalContractException(
            f"resolved_count={resolved_count} 与 resolved 长度 {len(resolved)} 不一致"
        )

    refs: list[ResolvedReference] = []
    for i, ref in enumerate(resolved):
        if not isinstance(ref, dict):
            raise InternalRetrievalContractException(f"resolved[{i}] 不是对象")
        identity = ref.get("source_identity")
        if not isinstance(identity, dict):
            raise InternalRetrievalContractException(f"resolved[{i}] 缺少 source_identity")
        missing = [f for f in _REQUIRED_HIT_IDENTITY_FIELDS[1:] if not identity.get(f)]
        if missing:
            raise InternalRetrievalContractException(
                f"resolved[{i}] source_identity 缺少字段: {', '.join(missing)}"
            )
        refs.append(
            ResolvedReference(
                source_identity=identity,
                minimal_excerpt=str(ref.get("minimal_excerpt") or ""),
                location=ref.get("location") or {},
                source_updated_at=str(ref.get("source_updated_at") or ""),
            )
        )

    return refs


async def _post_with_retry(
    path: str,
    body: dict,
    *,
    timeout: float,
    retry_max: int,
) -> httpx.Response:
    """POST 内部端点并处理可重试错误（有界指数退避）。

    Raises:
        InternalRetrievalUnavailableException: 可重试错误重试耗尽后
        InternalKnowledgeForbiddenException / UserDisabledException / InternalRetrievalContractException:
            fail-closed，不重试
    """
    base_url = settings.EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL.rstrip("/")
    url = f"{base_url}{path}"
    headers = _request_headers()

    attempts = retry_max + 1
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=body, headers=headers)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "Internal Retrieval 网络/超时错误（第 %d/%d 次）: url=%s, err=%s",
                attempt + 1,
                attempts,
                url,
                exc,
            )
            if attempt < retry_max:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                continue
            raise InternalRetrievalUnavailableException("内部知识检索服务暂不可用") from exc

        if response.status_code == 200:
            return response

        # 非 2xx：尝试读取契约错误信封（contracts/README.md §10）
        error_code, message = _parse_error_envelope(response)
        if error_code in _RETRYABLE_ERROR_CODES and attempt < retry_max:
            logger.warning(
                "Internal Retrieval 可重试错误（第 %d/%d 次）: code=%s",
                attempt + 1,
                attempts,
                error_code,
            )
            await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
            continue

        if error_code in _RETRYABLE_ERROR_CODES:
            raise InternalRetrievalUnavailableException(f"内部知识检索暂不可用（{error_code}）")

        _raise_contract_error(error_code, message)

    raise InternalRetrievalUnavailableException("内部知识检索重试耗尽")


def _parse_error_envelope(response: httpx.Response) -> tuple[str, str]:
    """从错误响应中提取 (error_code, message)；无法解析时返回通用错误。"""
    try:
        payload = response.json()
    except ValueError:
        return "INTERNAL_SERVER_ERROR", f"HTTP {response.status_code}"

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "INTERNAL_SERVER_ERROR", f"HTTP {response.status_code}"
    code = str(error.get("error_code") or "INTERNAL_SERVER_ERROR")
    message = str(error.get("message") or code)
    return code, message


async def search_retrieval(
    user_id: str,
    knowledge_base_ids: list[str],
    query: str,
    *,
    limit: int = 20,
    filters: dict | None = None,
) -> dict:
    """调用 Internal Retrieval 执行受限多 KB 检索。

    Args:
        user_id: Platform User UUID（仅作为实时授权主体）
        knowledge_base_ids: 全部目标 KB UUID（均需当前 READ 权限，任一无权整次失败）
        query: 仅用于内部检索的查询文本
        limit: 跨全部目标 KB 的最大命中数（1-100）
        filters: 可选检索过滤器（document_ids/languages/updated_since/updated_until）

    Returns:
        RetrievalSearchResult：按契约校验后的命中（minimal_excerpt 仅在内存）

    Raises:
        InternalKnowledgeForbiddenException: 任一 KB 当前不可读（fail-closed）
        InternalRetrievalUnavailableException: 瞬时不可用重试耗尽（可重试）
        InternalRetrievalContractException: 响应不符合契约
        UserDisabledException: 用户已禁用
    """
    body = {
        "contract_version": RETRIEVAL_CONTRACT_VERSION,
        "user_id": user_id,
        "knowledge_base_ids": knowledge_base_ids,
        "query": query,
        "purpose": "research_retrieval",
        "limit": limit,
    }
    if filters:
        body["filters"] = filters

    response = await _post_with_retry(
        "/internal/v1/retrieval/search",
        body,
        timeout=settings.EVIDSIGHT_INTERNAL_RETRIEVAL_TIMEOUT_SECONDS,
        retry_max=settings.EVIDSIGHT_INTERNAL_RETRIEVAL_RETRY_MAX,
    )
    return _parse_search_response(response.json())


async def resolve_retrieval(
    user_id: str,
    references: list[dict],
) -> list[ResolvedReference]:
    """按稳定身份精确重取当前仍可访问的内部正文（EvidenceResolveRequest）。

    Args:
        user_id: Platform User UUID（当前授权主体）
        references: InternalSourceIdentity 列表（kb/document/version/segment）

    Returns:
        list[ResolvedReference]：正文仅当前 Step 内存使用

    Raises:
        InternalRetrievalContractException: 响应不符合契约或来源不可用
        InternalRetrievalUnavailableException: 瞬时不可用重试耗尽
    """
    body = {
        "contract_version": RETRIEVAL_CONTRACT_VERSION,
        "user_id": user_id,
        "references": references,
        "purpose": "research_evidence_resolve",
    }

    response = await _post_with_retry(
        "/internal/v1/retrieval/resolve",
        body,
        timeout=settings.EVIDSIGHT_INTERNAL_RETRIEVAL_TIMEOUT_SECONDS,
        retry_max=settings.EVIDSIGHT_INTERNAL_RETRIEVAL_RETRY_MAX,
    )
    return _parse_resolve_response(response.json())
