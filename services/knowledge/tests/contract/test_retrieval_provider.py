"""Internal Retrieval & Evidence 契约 — Knowledge 作为 Provider 的验收测试（文档级）。

对齐 contracts/README.md §6-11、RAG_PIPELINE.md §7。
SDD 门禁：本文件只证明 Provider 构造的响应符合契约 Schema 与语义不变量；
`/internal/v1/retrieval/*` 端点与实时授权（服务身份 → Contract → 用户 active →
逐 KB READ → 检索）的端到端验收在权限感知 Provider 切片落地，届时补端点级测试。
"""

import pytest

from evidsight_contracts.loader import validator_for
from evidsight_contracts.semantics import (
    check_evidence_reference_source_identity,
    check_retrieval_response,
)

KB_A = "550e8400-e29b-41d4-a716-446655440010"
DOC_A = "550e8400-e29b-41d4-a716-446655440020"
VER_A1 = "550e8400-e29b-41d4-a716-446655440031"
SEG_A1 = "550e8400-e29b-41d4-a716-446655440041"
USER = "550e8400-e29b-41d4-a716-446655440001"


def _canonical_hit(segment_id: str = SEG_A1) -> dict:
    return {
        "hit_id": "550e8400-e29b-41d4-a716-446655440100",
        "knowledge_base_id": KB_A,
        "document_id": DOC_A,
        "document_version_id": VER_A1,
        "segment_id": segment_id,
        "document_display_name": "权限设计文档",
        "section_title": "权限矩阵",
        "location": {"page_number": 3},
        "minimal_excerpt": "KB 的 READ 权限决定该用户是否可检索。",
        "scores": [{"score_kind": "vector", "value": 0.87, "rank": 0}],
        "source_updated_at": "2026-08-03T09:00:00Z",
        "retrieved_at": "2026-08-04T12:00:00Z",
        "access_scope": "internal",
    }


class TestRetrievalProvider:
    def test_provider_can_produce_schema_compliant_retrieval_response(self):
        """GREEN：Provider 构造的单 KB 检索响应符合 RetrievalResponse 与 RetrievalHit Schema。"""
        response = {
            "contract_version": "1.0.0",
            "request_id": "01J00000000000000000000000",
            "results": [_canonical_hit()],
            "returned_count": 1,
            "has_more": False,
        }
        errors = list(validator_for("retrieval-response").iter_errors(response))
        assert not errors, f"Provider 构造的检索响应不符合契约:\n{errors}"
        assert not check_retrieval_response(response)

    def test_provider_never_emits_mismatched_returned_count(self):
        """语义不变量：returned_count 必须等于 results 长度，Provider 不得发出不一致响应。"""
        response = {
            "contract_version": "1.0.0",
            "request_id": "01J00000000000000000000000",
            "results": [_canonical_hit(), _canonical_hit("550e8400-e29b-41d4-a716-446655440042")],
            "returned_count": 1,
            "has_more": True,
        }
        # Schema 允许该结构，但语义不变量必须拒绝——Provider 不能发送
        assert check_retrieval_response(response)

    def test_provider_hit_exposes_no_internal_leak_fields(self):
        """§7：命中对象不得包含调试信息、查询计划、数据库字段、文件路径或缓存信息。"""
        hit = _canonical_hit()
        forbidden = {
            "query_plan",
            "chunk_text",
            "file_path",
            "cache_key",
            "embedding",
            "collection",
        }
        assert not (set(hit) & forbidden)
        errors = list(validator_for("retrieval-hit").iter_errors(hit))
        assert not errors, f"Provider 构造的命中不符合契约:\n{errors}"

    @pytest.mark.parametrize(
        "location",
        [
            {"section_path": ["第 1 章", "权限矩阵"]},
            {"char_span": {"start": 12, "end": 40}},
        ],
    )
    def test_provider_supports_all_location_kinds(self, location):
        """§11：页码、章节路径与字符区间三种可解释定位均可表达。"""
        hit = _canonical_hit()
        hit["location"] = location
        errors = list(validator_for("retrieval-hit").iter_errors(hit))
        assert not errors, f"定位 {location} 不符合契约:\n{errors}"

    def test_provider_can_produce_schema_compliant_evidence_reference(self):
        """GREEN：Provider（Research 侧持久化前）可构造符合 EvidenceReference 的内部引用。"""
        reference = {
            "evidence_id": "550e8400-e29b-41d4-a716-446655440050",
            "source_type": "internal",
            "source_identity": {
                "knowledge_base_id": KB_A,
                "document_id": DOC_A,
                "document_version_id": VER_A1,
                "segment_id": SEG_A1,
            },
            "display": {"title": "权限设计文档", "location_summary": "第 3 页"},
            "captured_at": "2026-08-04T12:05:00Z",
            "source_observed_at": "2026-08-03T09:00:00Z",
            "score_summary": {"best_score": 0.87, "score_kind": "vector", "rank": 0},
            "validity": "available",
        }
        errors = list(validator_for("evidence-reference").iter_errors(reference))
        assert not errors, f"Provider 构造的 EvidenceReference 不符合契约:\n{errors}"
        assert not check_evidence_reference_source_identity(reference)
