"""Synthesis 输出扩展 —— claims 结构单元测试。

对齐 RESEARCH_PIPELINE §8.1 / DATABASE.md §7.4 / ADR-009：
- Synthesis 输出新增 claims[]：statement / critical / certainty / qualification；
- 每个 claim 声明拟议 evidence_relations（supports/contradicts/context + confidence）；
- 校验：statement 非空、certainty 受控枚举、critical 为 bool、
  relation_type 受控枚举、confidence 0-1、evidence_index 合法。
"""

import json

import pytest
from app.pipeline.synthesizer import _parse_synthesis_output


def _claims_payload(claims: list[dict]) -> dict:
    return {
        "clusters": [
            {
                "theme": "量子计算威胁",
                "summary": "量子计算对 RSA 和 ECC 构成实际威胁。",
                "consensus_level": "strong",
                "supporting_evidence_indices": [0, 1],
                "conflicting_evidence_indices": [],
            }
        ],
        "claims": claims,
        "conflicts": [],
        "knowledge_gaps": [],
        "overall_assessment": "证据质量较高。",
    }


class TestSynthesisClaimsParse:
    def test_claims_合法解析(self):
        notes = _parse_synthesis_output(
            json.dumps(
                _claims_payload(
                    [
                        {
                            "statement": "量子计算对 RSA 构成实际威胁。",
                            "critical": True,
                            "certainty": "high",
                            "qualification": "需要工程化验证。",
                            "evidence_relations": [
                                {
                                    "evidence_index": 0,
                                    "relation_type": "supports",
                                    "confidence": 0.9,
                                }
                            ],
                        }
                    ]
                )
            ),
            expected_count=2,
        )
        assert len(notes.claims) == 1
        claim = notes.claims[0]
        assert claim.statement == "量子计算对 RSA 构成实际威胁。"
        assert claim.critical is True
        assert claim.certainty == "high"
        assert claim.qualification == "需要工程化验证。"
        assert claim.evidence_relations[0].evidence_index == 0
        assert claim.evidence_relations[0].relation_type == "supports"
        assert claim.evidence_relations[0].confidence == 0.9

    def test_claims可缺省_空数组(self):
        notes = _parse_synthesis_output(json.dumps(_claims_payload([])), expected_count=2)
        assert notes.claims == []

    def test_claims缺失字段_视为可选(self):
        notes = _parse_synthesis_output(
            json.dumps(
                _claims_payload(
                    [
                        {
                            "statement": "结论。",
                            "evidence_relations": [
                                {"evidence_index": 0, "relation_type": "supports"}
                            ],
                        }
                    ]
                )
            ),
            expected_count=2,
        )
        assert notes.claims[0].critical is False
        assert notes.claims[0].certainty == "medium"
        assert notes.claims[0].qualification is None
        assert notes.claims[0].evidence_relations[0].confidence == 0.0

    def test_relation_type缺失_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(
                    _claims_payload(
                        [
                            {
                                "statement": "x",
                                "evidence_relations": [{"evidence_index": 0}],
                            }
                        ]
                    )
                ),
                expected_count=2,
            )

    def test_statement为空_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(_claims_payload([{"statement": ""}])), expected_count=2
            )

    def test_certainty非法_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(_claims_payload([{"statement": "x", "certainty": "definite"}])),
                expected_count=2,
            )

    def test_relation_type非法_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(
                    _claims_payload(
                        [
                            {
                                "statement": "x",
                                "evidence_relations": [
                                    {"evidence_index": 0, "relation_type": "proves"}
                                ],
                            }
                        ]
                    )
                ),
                expected_count=2,
            )

    def test_confidence越界_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(
                    _claims_payload(
                        [
                            {
                                "statement": "x",
                                "evidence_relations": [
                                    {
                                        "evidence_index": 0,
                                        "relation_type": "supports",
                                        "confidence": 1.5,
                                    }
                                ],
                            }
                        ]
                    )
                ),
                expected_count=2,
            )

    def test_evidence_index越界_过滤(self):
        notes = _parse_synthesis_output(
            json.dumps(
                _claims_payload(
                    [
                        {
                            "statement": "x",
                            "evidence_relations": [
                                {"evidence_index": 99, "relation_type": "supports"}
                            ],
                        }
                    ]
                )
            ),
            expected_count=2,
        )
        assert notes.claims[0].evidence_relations == []

    def test_evidence_index非整数_拒绝(self):
        with pytest.raises(ValueError):
            _parse_synthesis_output(
                json.dumps(
                    _claims_payload(
                        [
                            {
                                "statement": "x",
                                "evidence_relations": [{"evidence_index": "a"}],
                            }
                        ]
                    )
                ),
                expected_count=2,
            )

    def test_claims非数组_拒绝(self):
        payload = _claims_payload([])
        payload["claims"] = {"statement": "x"}
        with pytest.raises(ValueError):
            _parse_synthesis_output(json.dumps(payload), expected_count=2)
