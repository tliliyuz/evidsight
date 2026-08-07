"""TaskStateResolver 预算停止终态测试 —— RESEARCH_PIPELINE §10.2/§10.3/§14。

预算停止不是自动成功：已有 Evidence 仍需通过完整度硬门槛（§10.2）与
evidence_completeness ≥ 0.70（§10.3）；达标可 partial，否则 failed（E3103）。
完整度取自已发布 Report Revision 的 evidence_completeness 摘要（§10.1，
三分项与总分由 Publisher 持久化，不由 LLM 直接给出）。
"""

from unittest.mock import MagicMock

from app.core.task_state_resolver import TaskStateResolver


def _make_step(status="completed", error_code=None, error_message=None, step_type="search"):
    step = MagicMock()
    step.status = status
    step.error_code = error_code
    step.error_message = error_message
    step.step_type = step_type
    return step


def _make_task(max_sources=10, budget_stopped_at=None):
    task = MagicMock()
    task.requirements = {"task_type": "analysis", "max_sources": max_sources}
    task.status = "running"
    task.cancel_requested_at = None
    task.budget_stopped_at = budget_stopped_at
    return task


def _published(score):
    return {
        "question_coverage": 1.0,
        "channel_success": 1.0,
        "claim_coverage": score,
        "score": score,
        "rule_version": 1,
    }


class TestBudgetStop:
    def setup_method(self):
        self.resolver = TaskStateResolver()

    def test_预算停止_已发布Revision完整度达标_返回partially_completed(self):
        """§14：预算停止后已发布 Revision 完整度 ≥ 0.70 且 Evidence ≥ 1 → partial。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [
            _make_step("completed", step_type="planning"),
            _make_step("completed", step_type="search"),
            _make_step("completed", step_type="fetch"),
        ]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=6, published_completeness=_published(0.80)
        )
        assert status == "partially_completed"
        assert err is None

    def test_预算停止_完整度不足_返回failed_E3103(self):
        """§10.3：已发布 Revision 完整度 < 0.70 → failed（E3103）。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [
            _make_step("completed", step_type="planning"),
            _make_step("completed", step_type="search"),
        ]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=3, published_completeness=_published(0.60)
        )
        assert status == "failed"
        assert err is not None
        assert err["error_code"] == "E3103"
        assert err["recoverable"] is False

    def test_预算停止_边界完整度刚好07_返回partially_completed(self):
        """§17.2 边界：evidence_completeness == 0.70 恰好达标。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=5, published_completeness=_published(0.70)
        )
        assert status == "partially_completed"

    def test_预算停止_无已发布Revision_返回failed(self):
        """§10.2 硬门槛：预算在 render 前停止 → 无已发布 Revision → failed。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=6, published_completeness=None
        )
        assert status == "failed"
        assert err is not None
        assert err["error_code"] == "E3103"

    def test_预算停止_零证据_返回failed(self):
        """§17.2 规则 9：零 Evidence 不得利用空集合通过。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=0, published_completeness=_published(0.90)
        )
        assert status == "failed"
        assert err["error_code"] == "E3103"

    def test_未预算停止_仍走正常运行守卫(self):
        """未触发预算停止时，phase 未全部尝试仍视为 running。"""
        task = _make_task(max_sources=10, budget_stopped_at=None)
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(
            task, steps, evidence_count=6, published_completeness=_published(0.90)
        )
        assert status == "running"
