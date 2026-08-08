"""Pydantic 参考模型 smoke 验证：每个新契约 Schema 的有效 Fixture 必须能被对应模型解析。

参考模型由 Schema 手工维护（生成器工具链在 M4 落地），本测试防止模型在有效数据上
与 Schema/Fixture 漂移。结构性拒绝由权威 jsonschema 测试（test_fixture_validation.py）
覆盖；pydantic 默认存在类型强转，不在此与 JSON Schema 严格类型做逐一比对。
"""

import pytest
from evidsight_contracts.loader import list_fixtures, load_fixture
from evidsight_contracts.v1 import (
    evidence_reference,
    evidence_relation,
    evidence_resolve_request,
    evidence_resolve_response,
    retrieval_hit,
    retrieval_request,
    retrieval_response,
)
from pydantic import BaseModel

MODELS: dict[str, type[BaseModel]] = {
    "retrieval-request": retrieval_request.RetrievalRequest,
    "retrieval-response": retrieval_response.RetrievalResponse,
    "retrieval-hit": retrieval_hit.RetrievalHit,
    "evidence-resolve-request": evidence_resolve_request.EvidenceResolveRequest,
    "evidence-resolve-response": evidence_resolve_response.EvidenceResolveResponse,
    "evidence-reference": evidence_reference.EvidenceReference,
    "evidence-relation": evidence_relation.EvidenceRelation,
}


@pytest.mark.parametrize(
    "schema_name, fixture_name",
    [(name, fixture) for name in MODELS for fixture in list_fixtures(name, "valid")],
)
def test_reference_model_parses_valid_fixture(schema_name, fixture_name):
    """有效 Fixture 能被对应参考模型解析。"""
    fixture = load_fixture(schema_name, "valid", fixture_name)
    parsed = MODELS[schema_name].model_validate(fixture)
    assert parsed is not None
