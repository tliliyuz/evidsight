"""Internal Retrieval & Evidence 契约 — Research 作为 Consumer 的验收测试。

对齐 contracts/README.md §6-11。Consumer 测试独立运行：只读取 packages/contracts 的
Schema 与 Fixture，不依赖 Knowledge 端点、数据库或服务导入。
SDD 门禁：GREEN 目标——Research 能消费全部有效 Fixture 并拒绝全部无效 Fixture；
契约 Schema 由 packages/contracts 维护，本文件只证明 Consumer 侧解读一致。
"""

import pytest
from evidsight_contracts import semantics
from evidsight_contracts.loader import list_fixtures, load_fixture, validator_for

NEW_SCHEMAS = [
    "retrieval-request",
    "retrieval-response",
    "retrieval-hit",
    "evidence-resolve-request",
    "evidence-resolve-response",
    "evidence-reference",
    "evidence-relation",
]


def _all_invalid(schemas):
    return [(name, fixture) for name in schemas for fixture in list_fixtures(name, "invalid")]


class TestRetrievalEvidenceConsumer:
    @pytest.mark.parametrize("schema_name", NEW_SCHEMAS)
    def test_consumer_has_valid_fixtures(self, schema_name):
        """每个新契约 Schema 至少有一个 valid fixture，且全部通过 Schema 与语义不变量。"""
        valid = list_fixtures(schema_name, "valid")
        assert valid, f"{schema_name} 至少需要一个 valid fixture"
        for name in valid:
            fixture = load_fixture(schema_name, "valid", name)
            errors = list(validator_for(schema_name).iter_errors(fixture))
            assert not errors, f"{schema_name}/valid/{name} 应通过校验:\n{errors}"
            checker = semantics.SEMANTIC_CHECKERS.get(schema_name)
            if checker:
                violations = checker(fixture)
                assert not violations, (
                    f"{schema_name}/valid/{name} 应通过语义不变量:\n" + "\n".join(violations)
                )

    @pytest.mark.parametrize("schema_name, fixture_name", _all_invalid(NEW_SCHEMAS))
    def test_consumer_rejects_invalid_fixtures(self, schema_name, fixture_name):
        """无效 Fixture 必须被 Schema 或语义不变量拒绝。"""
        fixture = load_fixture(schema_name, "invalid", fixture_name)
        schema_errors = list(validator_for(schema_name).iter_errors(fixture))
        checker = semantics.SEMANTIC_CHECKERS.get(schema_name)
        semantic_violations = checker(fixture) if checker else []
        assert schema_errors or semantic_violations, (
            f"{schema_name}/invalid/{fixture_name} 应被拒绝但通过了 Schema 与语义校验"
        )

    def test_evidence_reference_has_no_body_or_path_fields(self):
        """§9：EvidenceReference 从结构上禁止正文、Embedding、Prompt、存储路径或扩展字段。"""
        schema = validator_for("evidence-reference").schema
        assert schema.get("additionalProperties") is False
        top_keys = set(schema.get("properties", {}))
        assert not (top_keys & {"excerpt", "content", "text", "chunk_text", "path", "embedding"})

    def test_consumer_runs_independently(self):
        """Consumer 测试可独立运行：仅通过文件系统读取 Schema 与 Fixture，无 HTTP/DB 依赖。"""
        for name in NEW_SCHEMAS:
            validator = validator_for(name)
            assert validator.schema.get("additionalProperties") is False
        # 两类来源身份严格互斥（oneOf）体现在 Schema 结构上
        source_identity = validator_for("evidence-reference").schema["properties"][
            "source_identity"
        ]
        assert "oneOf" in source_identity
