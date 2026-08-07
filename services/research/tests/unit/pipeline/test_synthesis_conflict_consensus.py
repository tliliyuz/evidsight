"""合成冲突共识规则单元测试 —— 对齐 RESEARCH_PIPELINE §9.5 与 PRD FR-EV-003。

门禁「冲突来源不会被合成为无条件确定结论」的程序化校验：
- cluster 含非空 conflicting_evidence_indices 时，其 consensus_level 不得为 strong；
- 无冲突证据的 cluster 允许 strong（真共识）；
- 冲突 cluster 允许 moderate / weak（限定结论，正确降级）。
"""

import json

import pytest
from app.pipeline.synthesizer import _parse_synthesis_output


def _cluster_payload(consensus_level: str, conflicting: list[int], supporting: list[int]) -> dict:
    return {
        "clusters": [
            {
                "theme": "量子计算威胁",
                "summary": "量子计算对 RSA 和 ECC 构成实际威胁。",
                "consensus_level": consensus_level,
                "supporting_evidence_indices": supporting,
                "conflicting_evidence_indices": conflicting,
            }
        ],
        "conflicts": [],
        "knowledge_gaps": [],
        "overall_assessment": "证据质量较高。",
    }


class TestConflictConsensusRule:
    def test_含冲突证据_consensus_level_strong_拒绝(self):
        """§9.5：存在 contradicts 时不得合成为无条件确定结论。

        含冲突证据的 cluster 标记 strong（无条件确定）必须被拒绝。
        """
        raw = json.dumps(_cluster_payload("strong", conflicting=[2], supporting=[0, 1]))
        with pytest.raises(ValueError):
            _parse_synthesis_output(raw, expected_count=3)

    def test_含冲突证据_consensus_level_moderate_允许(self):
        """冲突 cluster 允许 moderate，即结论被限定而非无条件确定。"""
        notes = _parse_synthesis_output(
            json.dumps(_cluster_payload("moderate", conflicting=[2], supporting=[0, 1])),
            expected_count=3,
        )
        assert notes.clusters[0].consensus_level == "moderate"

    def test_含冲突证据_consensus_level_weak_允许(self):
        """冲突 cluster 允许 weak，结论被降级表达。"""
        notes = _parse_synthesis_output(
            json.dumps(_cluster_payload("weak", conflicting=[2], supporting=[0, 1])),
            expected_count=3,
        )
        assert notes.clusters[0].consensus_level == "weak"

    def test_无冲突证据_consensus_level_strong_允许(self):
        """无冲突证据时允许 strong（真共识，多个来源共同支持）。"""
        notes = _parse_synthesis_output(
            json.dumps(_cluster_payload("strong", conflicting=[], supporting=[0, 1])),
            expected_count=3,
        )
        assert notes.clusters[0].consensus_level == "strong"

    def test_冲突索引与支持索引重合_仍拒绝_strong(self):
        """即使同一证据同时被列为主支持与冲突，只要有冲突标记就不允许 strong。"""
        raw = json.dumps(_cluster_payload("strong", conflicting=[1], supporting=[0, 1]))
        with pytest.raises(ValueError):
            _parse_synthesis_output(raw, expected_count=3)
