"""人工评估记录处理单元测试"""

import json
from datetime import datetime, timezone

import pytest

from app.evaluation.manual import (
    aggregate_manual_records,
    compare_rounds,
    load_all_manual_rounds,
    load_manual_records,
    validate_manual_record,
)
from app.evaluation.models import ManualAggregationResult, ManualDimensionScore, ManualEvaluationRecord


class TestValidateManualRecord:
    """测试人工评估记录校验。"""

    def test_完整有效记录校验通过(self):
        data = {
            "round": 1,
            "task_id": "task-1",
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 4, "comment": ""},
                {"dimension": "引用准确性", "score": 3, "comment": ""},
                {"dimension": "综合质量", "score": 4, "comment": ""},
                {"dimension": "可读性", "score": 4, "comment": ""},
            ],
            "overall_score": 3.75,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

        record = validate_manual_record(data)

        assert isinstance(record, ManualEvaluationRecord)
        assert record.round == 1
        assert record.task_id == "task-1"
        assert len(record.scores) == 4

    def test_缺少必要字段抛出异常(self):
        data = {"round": 1}

        with pytest.raises(ValueError) as exc_info:
            validate_manual_record(data)

        assert "task_id" in str(exc_info.value)

    def test_评分超出范围抛出异常(self):
        data = {
            "round": 1,
            "task_id": "task-1",
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 6},
                {"dimension": "引用准确性", "score": 3},
                {"dimension": "综合质量", "score": 4},
                {"dimension": "可读性", "score": 4},
            ],
            "overall_score": 4.25,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

        with pytest.raises(ValueError) as exc_info:
            validate_manual_record(data)

        assert "结构完整性" in str(exc_info.value)
        assert "6" in str(exc_info.value)

    def test_浮点评分校验通过且不被截断(self):
        data = {
            "round": 1,
            "task_id": "task-1",
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "aggregated",
            "scores": [
                {"dimension": "结构完整性", "score": 4.7, "comment": ""},
                {"dimension": "引用准确性", "score": 4.3, "comment": ""},
                {"dimension": "综合质量", "score": 4.3, "comment": ""},
                {"dimension": "可读性", "score": 5.0, "comment": ""},
            ],
            "overall_score": 4.575,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

        record = validate_manual_record(data)

        assert record.scores[0].score == pytest.approx(4.7)
        assert record.scores[1].score == pytest.approx(4.3)
        assert record.overall_score == pytest.approx(4.575)

    def test_缺少维度抛出异常(self):
        data = {
            "round": 1,
            "task_id": "task-1",
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 4},
                {"dimension": "引用准确性", "score": 3},
                {"dimension": "综合质量", "score": 4},
            ],
            "overall_score": 3.67,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

        with pytest.raises(ValueError) as exc_info:
            validate_manual_record(data)

        assert "缺少评估维度" in str(exc_info.value)
        assert "可读性" in str(exc_info.value)

    def test_重复维度抛出异常(self):
        data = {
            "round": 1,
            "task_id": "task-1",
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 4},
                {"dimension": "结构完整性", "score": 3},
                {"dimension": "引用准确性", "score": 3},
                {"dimension": "综合质量", "score": 4},
                {"dimension": "可读性", "score": 4},
            ],
            "overall_score": 3.75,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

        with pytest.raises(ValueError) as exc_info:
            validate_manual_record(data)

        assert "重复评估维度" in str(exc_info.value)


class TestAggregateManualRecords:
    """测试人工评估聚合。"""

    def test_两条记录聚合_维度均值与总体均值正确(self):
        records = [
            ManualEvaluationRecord(
                round=1,
                task_id="task-1",
                topic="T1",
                task_type="analysis",
                rater="a",
                scores=[
                    ManualDimensionScore("结构完整性", 4),
                    ManualDimensionScore("引用准确性", 3),
                    ManualDimensionScore("综合质量", 4),
                    ManualDimensionScore("可读性", 4),
                ],
                overall_score=3.75,
                evaluated_at=datetime.now(timezone.utc),
            ),
            ManualEvaluationRecord(
                round=1,
                task_id="task-2",
                topic="T2",
                task_type="comparison",
                rater="a",
                scores=[
                    ManualDimensionScore("结构完整性", 2),
                    ManualDimensionScore("引用准确性", 3),
                    ManualDimensionScore("综合质量", 3),
                    ManualDimensionScore("可读性", 4),
                ],
                overall_score=3.0,
                evaluated_at=datetime.now(timezone.utc),
            ),
        ]

        result = aggregate_manual_records(records)

        assert result.record_count == 2
        assert result.dimension_means["结构完整性"] == pytest.approx(3.0)
        assert result.dimension_means["引用准确性"] == pytest.approx(3.0)
        assert result.dimension_means["综合质量"] == pytest.approx(3.5)
        assert result.dimension_means["可读性"] == pytest.approx(4.0)
        assert result.overall_mean == pytest.approx(3.375)
        assert result.min_dimension == "结构完整性"
        assert result.min_dimension_mean == pytest.approx(3.0)

    def test_空列表返回零值聚合(self):
        result = aggregate_manual_records([])

        assert result == ManualAggregationResult(
            record_count=0,
            dimension_means={
                "结构完整性": 0.0,
                "引用准确性": 0.0,
                "综合质量": 0.0,
                "可读性": 0.0,
            },
            overall_mean=0.0,
            task_type_means={},
            round_means={},
            min_dimension="结构完整性",
            min_dimension_mean=0.0,
        )


class TestCompareRounds:
    """测试人工评估轮次对比。"""

    def test_第二轮较第一轮提升(self):
        baseline = aggregate_manual_records([
            ManualEvaluationRecord(
                round=1,
                task_id="task-1",
                topic="T1",
                task_type="analysis",
                rater="a",
                scores=[
                    ManualDimensionScore("结构完整性", 3),
                    ManualDimensionScore("引用准确性", 3),
                    ManualDimensionScore("综合质量", 3),
                    ManualDimensionScore("可读性", 3),
                ],
                overall_score=3.0,
                evaluated_at=datetime.now(timezone.utc),
            ),
        ])
        current = aggregate_manual_records([
            ManualEvaluationRecord(
                round=2,
                task_id="task-1",
                topic="T1",
                task_type="analysis",
                rater="a",
                scores=[
                    ManualDimensionScore("结构完整性", 4),
                    ManualDimensionScore("引用准确性", 4),
                    ManualDimensionScore("综合质量", 4),
                    ManualDimensionScore("可读性", 4),
                ],
                overall_score=4.0,
                evaluated_at=datetime.now(timezone.utc),
            ),
        ])

        comparison = compare_rounds(current, baseline)

        assert comparison["baseline_overall_mean"] == pytest.approx(3.0)
        assert comparison["current_overall_mean"] == pytest.approx(4.0)
        assert comparison["overall_delta"] == pytest.approx(1.0)
        assert comparison["dimension_deltas"]["结构完整性"] == pytest.approx(1.0)


class TestLoadManualRecords:
    """测试从目录加载人工评估 JSON 记录。"""

    def _build_valid_record(self, task_id: str = "task-1") -> dict:
        return {
            "round": 1,
            "task_id": task_id,
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 4, "comment": ""},
                {"dimension": "引用准确性", "score": 3, "comment": ""},
                {"dimension": "综合质量", "score": 4, "comment": ""},
                {"dimension": "可读性", "score": 4, "comment": ""},
            ],
            "overall_score": 3.75,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

    def test_加载单个对象文件(self, tmp_path):
        record_file = tmp_path / "analysis_task1_rater-a.json"
        record_file.write_text(json.dumps(self._build_valid_record(), ensure_ascii=False), encoding="utf-8")

        records = load_manual_records(tmp_path)

        assert len(records) == 1
        assert records[0].task_id == "task-1"
        assert records[0].round == 1

    def test_加载数组文件(self, tmp_path):
        array_file = tmp_path / "round_records.json"
        array_file.write_text(
            json.dumps([self._build_valid_record("task-1"), self._build_valid_record("task-2")], ensure_ascii=False),
            encoding="utf-8",
        )

        records = load_manual_records(tmp_path)

        assert len(records) == 2
        assert records[0].task_id == "task-1"
        assert records[1].task_id == "task-2"

    def test_跳过无效JSON文件(self, tmp_path):
        valid_file = tmp_path / "valid.json"
        valid_file.write_text(json.dumps(self._build_valid_record(), ensure_ascii=False), encoding="utf-8")
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not json", encoding="utf-8")

        records = load_manual_records(tmp_path)

        assert len(records) == 1
        assert records[0].task_id == "task-1"

    def test_跳过校验失败记录(self, tmp_path):
        valid_file = tmp_path / "valid.json"
        valid_file.write_text(json.dumps(self._build_valid_record(), ensure_ascii=False), encoding="utf-8")
        invalid_file = tmp_path / "invalid_score.json"
        bad_record = self._build_valid_record()
        bad_record["scores"][0]["score"] = 10
        invalid_file.write_text(json.dumps(bad_record, ensure_ascii=False), encoding="utf-8")

        records = load_manual_records(tmp_path)

        assert len(records) == 1
        assert records[0].task_id == "task-1"

    def test_目录不存在抛出异常(self, tmp_path):
        non_existent = tmp_path / "not_exists"

        with pytest.raises(ValueError) as exc_info:
            load_manual_records(non_existent)

        assert "目录不存在" in str(exc_info.value)


class TestLoadAllManualRounds:
    """测试从根目录加载所有 round* 子目录的人工评估记录。"""

    def _build_valid_record(self, round_num: int, task_id: str = "task-1") -> dict:
        return {
            "round": round_num,
            "task_id": task_id,
            "topic": "量子计算",
            "task_type": "analysis",
            "rater": "rater-a",
            "scores": [
                {"dimension": "结构完整性", "score": 4, "comment": ""},
                {"dimension": "引用准确性", "score": 3, "comment": ""},
                {"dimension": "综合质量", "score": 4, "comment": ""},
                {"dimension": "可读性", "score": 4, "comment": ""},
            ],
            "overall_score": 3.75,
            "evaluated_at": "2026-06-27T10:00:00+00:00",
        }

    def test_加载多个round子目录(self, tmp_path):
        round1_dir = tmp_path / "round1"
        round1_dir.mkdir()
        round2_dir = tmp_path / "round2"
        round2_dir.mkdir()
        (round1_dir / "record.json").write_text(
            json.dumps(self._build_valid_record(1, "task-1"), ensure_ascii=False),
            encoding="utf-8",
        )
        (round2_dir / "record.json").write_text(
            json.dumps(self._build_valid_record(2, "task-2"), ensure_ascii=False),
            encoding="utf-8",
        )

        records = load_all_manual_rounds(tmp_path)

        assert len(records) == 2
        assert {r.task_id for r in records} == {"task-1", "task-2"}
        assert {r.round for r in records} == {1, 2}

    def test_忽略非round目录(self, tmp_path):
        round1_dir = tmp_path / "round1"
        round1_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (round1_dir / "record.json").write_text(
            json.dumps(self._build_valid_record(1), ensure_ascii=False),
            encoding="utf-8",
        )
        (other_dir / "record.json").write_text(
            json.dumps(self._build_valid_record(1, "ignored"), ensure_ascii=False),
            encoding="utf-8",
        )

        records = load_all_manual_rounds(tmp_path)

        assert len(records) == 1
        assert records[0].task_id == "task-1"

    def test_空根目录返回空列表(self, tmp_path):
        records = load_all_manual_rounds(tmp_path)

        assert records == []

    def test_目录不存在抛出异常(self, tmp_path):
        non_existent = tmp_path / "not_exists"

        with pytest.raises(ValueError) as exc_info:
            load_all_manual_rounds(non_existent)

        assert "目录不存在" in str(exc_info.value)
