"""AC 验证指标纯函数单元测试。

覆盖 M3 退出门禁的 PRD AC-001/003/004/010 对应计算逻辑：
- AC-001：报告章节 [来源N] 引用闭合校验（关键结论有效引用率 ≥ 90%）；
- AC-003：排除用户主动取消后的任务成功率（≥ 95%）；
- AC-004：恢复演练结果成功率（≥ 95%）；
- AC-010：Evidence 分型与定位/URL/获取时间可追溯性（100%）。
"""

import pytest

from app.evaluation.ac_metrics import (
    CITATION_RE,
    check_evidence_traceability,
    compute_recovery_success_rate,
    compute_task_success_rate,
    evaluate_citation_validity,
    extract_citations,
)
class TestExtractCitations:
    """正文 [来源N] 引用提取。"""

    def test_提取多个引用(self):
        assert extract_citations("结论A[来源0]，结论B[来源1][来源2]") == [0, 1, 2]

    def test_无引用返回空(self):
        assert extract_citations("没有任何引用") == []

    def test_空正文返回空(self):
        assert extract_citations("") == []
        assert extract_citations(None) == []

    def test_非标准格式不误判(self):
        assert extract_citations("[来源 0][来源0,1][来源N]") == []

    def test_正则可编译(self):
        assert CITATION_RE.pattern


class TestEvaluateCitationValidity:
    """AC-001 引用闭合校验：每个 [来源N] 必须映射到该 section 实际关联的 Evidence。"""

    def _sections(self):
        return [
            {"id": 1, "content": "结论一[来源0]，结论二[来源1]"},
            {"id": 2, "content": "结论三[来源2]"},
        ]

    def test_全部闭合_通过(self):
        # section1 关联 evidence A(→index0) 与 B(→index1)；section2 关联 C(→index2)
        section_evidence = {1: [101, 102], 2: [103]}
        evidence_index = {101: 0, 102: 1, 103: 2}
        valid, total, rate = evaluate_citation_validity(
            self._sections(), section_evidence, evidence_index
        )
        assert valid == 3
        assert total == 3
        assert rate == pytest.approx(1.0)

    def test_引用未关联_计入无效(self):
        # section1 只关联 A(→index0)，正文引用 [来源1] 未闭合
        section_evidence = {1: [101], 2: [103]}
        evidence_index = {101: 0, 102: 1, 103: 2}
        valid, total, rate = evaluate_citation_validity(
            self._sections(), section_evidence, evidence_index
        )
        assert valid == 2
        assert total == 3
        assert rate == pytest.approx(2 / 3)

    def test_引用index不存在_计入无效(self):
        section_evidence = {1: [101], 2: [103]}
        # evidence 102 未被 graph 收录（无 index 映射）
        evidence_index = {101: 0, 103: 2}
        valid, total, _ = evaluate_citation_validity(
            self._sections(), section_evidence, evidence_index
        )
        assert valid == 2
        assert total == 3

    def test_无引用_rate为0(self):
        sections = [{"id": 1, "content": "无引用正文"}]
        valid, total, rate = evaluate_citation_validity(
            sections, {1: [101]}, {101: 0}
        )
        assert valid == 0
        assert total == 0
        assert rate == 0.0


class TestComputeTaskSuccessRate:
    """AC-003 成功率：completed + partially_completed 为成功，canceled 从分母排除。"""

    def test_达标(self):
        success, denominator, rate = compute_task_success_rate({
            "completed": 90,
            "partially_completed": 5,
            "failed": 5,
            "canceled": 3,  # 用户主动取消，排除
        })
        assert success == 95
        assert denominator == 100
        assert rate == pytest.approx(0.95)

    def test_全部成功(self):
        _, _, rate = compute_task_success_rate({
            "completed": 20,
            "partially_completed": 0,
            "failed": 0,
        })
        assert rate == pytest.approx(1.0)

    def test_空样本_rate为0(self):
        _, _, rate = compute_task_success_rate({})
        assert rate == 0.0

    def test_取消不进入分母(self):
        _, denominator, _ = compute_task_success_rate({
            "completed": 0,
            "partially_completed": 0,
            "failed": 1,
            "canceled": 100,
        })
        assert denominator == 1


class TestComputeRecoverySuccessRate:
    """AC-004 恢复演练成功率。"""

    def test_全部恢复(self):
        success, total, rate = compute_recovery_success_rate([True, True, True])
        assert success == 3
        assert total == 3
        assert rate == pytest.approx(1.0)

    def test_部分恢复(self):
        success, total, rate = compute_recovery_success_rate([True, False, True])
        assert success == 2
        assert total == 3
        assert rate == pytest.approx(2 / 3)

    def test_空样本_rate为0(self):
        success, total, rate = compute_recovery_success_rate([])
        assert success == 0
        assert total == 0
        assert rate == 0.0


class TestCheckEvidenceTraceability:
    """AC-010 可追溯性：source_type 存在；internal 可定位，web 展示 URL 与获取时间。"""

    def test_internal_完整可追溯(self):
        traceable, total, problems = check_evidence_traceability([
            {
                "source_type": "internal",
                "knowledge_base_id": "kb-1",
                "document_id": "doc-1",
                "document_version_id": "ver-1",
                "segment_id": "seg-1",
                "location_summary": "第 1 页",
                "canonical_url_snapshot": None,
                "fetched_at_snapshot": None,
            }
        ])
        assert traceable == 1
        assert total == 1
        assert problems == []

    def test_internal_缺定位_不可追溯(self):
        traceable, total, problems = check_evidence_traceability([
            {
                "source_type": "internal",
                "knowledge_base_id": "kb-1",
                "document_id": None,  # 缺 document_id
                "document_version_id": "ver-1",
                "segment_id": "seg-1",
                "location_summary": None,  # 缺位置
            }
        ])
        assert traceable == 0
        assert total == 1
        assert len(problems) == 1

    def test_web_完整可追溯(self):
        traceable, total, _ = check_evidence_traceability([
            {
                "source_type": "web",
                "canonical_url_snapshot": "https://example.com/a",
                "fetched_at_snapshot": "2026-01-01T00:00:00Z",
            }
        ])
        assert traceable == 1
        assert total == 1

    def test_web_缺获取时间_不可追溯(self):
        # PRD AC-010：外部证据必须展示 URL 与获取时间，fetched_at 缺失即不可追溯
        traceable, total, problems = check_evidence_traceability([
            {
                "source_type": "web",
                "canonical_url_snapshot": "https://example.com/a",
                "fetched_at_snapshot": None,
            }
        ])
        assert traceable == 0
        assert total == 1
        assert len(problems) == 1

    def test_未知来源类型_不可追溯(self):
        traceable, total, _ = check_evidence_traceability([
            {"source_type": None}
        ])
        assert traceable == 0
        assert total == 1

    def test_空列表(self):
        traceable, total, problems = check_evidence_traceability([])
        assert traceable == 0
        assert total == 0
        assert problems == []


class TestFrozenEvalSet:
    """冻结评估集 JSON 结构（AC-003/AC-004 输入格式）。"""

    def test_评估集结构合法(self):
        from pathlib import Path

        eval_set_path = (
            Path(__file__).resolve().parent.parent.parent.parent / "tests" / "eval"
            / "research_eval_set.json"
        )
        assert eval_set_path.exists(), f"冻结评估集缺失: {eval_set_path}"

        import json

        data = json.loads(eval_set_path.read_text(encoding="utf-8"))
        assert isinstance(data, list) and len(data) > 0
        for entry in data:
            assert entry.get("id") is not None
            assert entry.get("topic")
            assert entry.get("task_type") in {
                "comparison", "explainer", "analysis"
            }

