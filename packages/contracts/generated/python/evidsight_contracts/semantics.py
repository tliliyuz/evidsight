"""Internal Contract 语义不变量校验（跨字段约束）。

纯 JSON Schema 无法表达跨字段不变量：数组长度对字段（returned_count vs results）、
时间先后（updated_since <= updated_until）、来源类型与身份匹配（source_type vs
source_identity）。本模块提供共享纯函数，供契约自检、Research Consumer 与
Knowledge Provider 复用，保证双方对同一规则理解一致。

约定：每个函数接收完整文档（dict），返回违反描述列表；空列表表示通过。
文档不是 dict 或字段类型不符合时返回空列表（结构校验由 Schema 负责）。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Union

SchemaChecker = Callable[[Union[dict, None]], List[str]]


def check_retrieval_request(request) -> List[str]:
    """filters.updated_since 必须早于或等于 filters.updated_until。

    RFC3339 UTC 采用固定宽度格式与 Z 结尾，字符串词法序与时间序一致。
    """
    if not isinstance(request, dict):
        return []
    filters = request.get("filters")
    if not isinstance(filters, dict):
        return []
    since = filters.get("updated_since")
    until = filters.get("updated_until")
    if isinstance(since, str) and isinstance(until, str) and since > until:
        return ["filters.updated_since 必须早于或等于 filters.updated_until"]
    return []


def check_retrieval_response(response) -> List[str]:
    """returned_count 必须等于 results 长度。"""
    if not isinstance(response, dict):
        return []
    returned_count = response.get("returned_count")
    results = response.get("results")
    if isinstance(returned_count, int) and isinstance(results, list):
        if returned_count != len(results):
            return ["returned_count 必须等于 results 长度"]
    return []


def check_evidence_reference_source_identity(reference) -> List[str]:
    """source_type 必须与 source_identity 的来源种类匹配，禁止伪装来源。"""
    if not isinstance(reference, dict):
        return []
    source_type = reference.get("source_type")
    identity = reference.get("source_identity")
    if not isinstance(identity, dict):
        return []
    if source_type == "internal":
        if "url" in identity or "fetched_at" in identity:
            return ["source_type=internal 时 source_identity 不得包含 url/fetched_at"]
    if source_type == "web":
        if "knowledge_base_id" in identity or "document_id" in identity:
            return ["source_type=web 时 source_identity 不得包含内部来源字段"]
    return []


SEMANTIC_CHECKERS: Dict[str, SchemaChecker] = {
    "retrieval-request": check_retrieval_request,
    "retrieval-response": check_retrieval_response,
    "evidence-reference": check_evidence_reference_source_identity,
}
