"""Evidence Graph Build —— claims 输出扩展单元测试。

对齐 RESEARCH_PIPELINE §9 / DATABASE.md §7.4 / ADR-009：
- run_evidence_graph 从 Synthesis output 读取 claims[]；
- 将每个 claim 的 evidence_index 关联到 Graph item 的 evidence_item_id；
- graph["claims"] 携带 statement/critical/certainty/qualification 与
  relations[{evidence_item_id, evidence_index, relation_type, confidence}]；
- 越界/非整数 evidence_index 被过滤（防御性），不阻断 Graph 构建。
"""

from app.pipeline.evidence_graph import run_evidence_graph

from .test_evidence_graph import _seed_evidence_graph_task, _valid_synthesis_output


def _claims_synthesis_output() -> dict:
    output = _valid_synthesis_output()
    output["claims"] = [
        {
            "statement": "量子计算对 RSA 构成实际威胁。",
            "critical": True,
            "certainty": "high",
            "qualification": "需要工程化验证。",
            "evidence_relations": [
                {"evidence_index": 0, "relation_type": "supports", "confidence": 0.9},
                {"evidence_index": 1, "relation_type": "context", "confidence": 0.6},
            ],
        },
        {
            "statement": "NIST 后量子标准化存在时间分歧。",
            "critical": False,
            "certainty": "medium",
            "evidence_relations": [
                {"evidence_index": 1, "relation_type": "supports", "confidence": 0.7},
            ],
        },
    ]
    return output


class TestEvidenceGraphClaims:
    async def test_graph包含claims且关联evidence_item_id(self, db_session):
        task, step = await _seed_evidence_graph_task(
            db_session,
            max_sources=3,
            evidence_count=3,
            synthesis_output=_claims_synthesis_output(),
        )
        output = await run_evidence_graph(task, step, db_session, _FakeSSE())
        graph = output["graph"]
        assert len(graph["claims"]) == 2

        claim0 = graph["claims"][0]
        assert claim0["statement"] == "量子计算对 RSA 构成实际威胁。"
        assert claim0["critical"] is True
        assert claim0["certainty"] == "high"
        assert claim0["qualification"] == "需要工程化验证。"
        assert len(claim0["relations"]) == 2
        rel0 = claim0["relations"][0]
        assert rel0["relation_type"] == "supports"
        assert rel0["confidence"] == 0.9
        assert rel0["evidence_index"] == 0
        assert rel0["evidence_item_id"] is not None  # 关联到 Graph item

        # relation 的 evidence_item_id 必须等于对应 Graph item 的 evidence_item_id
        item0 = graph["items"][0]
        assert rel0["evidence_item_id"] == item0["evidence_item_id"]

    async def test_claims越界索引被过滤(self, db_session):
        output = _claims_synthesis_output()
        output["claims"][0]["evidence_relations"] = [
            {"evidence_index": 99, "relation_type": "supports"}
        ]
        task, step = await _seed_evidence_graph_task(
            db_session, max_sources=2, evidence_count=2, synthesis_output=output
        )
        result = await run_evidence_graph(task, step, db_session, _FakeSSE())
        assert result["graph"]["claims"][0]["relations"] == []

    async def test_claims缺省_输出空数组(self, db_session):
        task, step = await _seed_evidence_graph_task(
            db_session, synthesis_output=_valid_synthesis_output()
        )
        result = await run_evidence_graph(task, step, db_session, _FakeSSE())
        assert result["graph"]["claims"] == []

    async def test_claims非数组_不阻断(self, db_session):
        output = _valid_synthesis_output()
        output["claims"] = {"statement": "x"}
        task, step = await _seed_evidence_graph_task(
            db_session, max_sources=2, evidence_count=2, synthesis_output=output
        )
        result = await run_evidence_graph(task, step, db_session, _FakeSSE())
        assert result["graph"]["claims"] == []


class _FakeSSE:
    async def publish(self, event, data):
        pass
