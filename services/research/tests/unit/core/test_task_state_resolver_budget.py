"""TaskStateResolver 预算停止终态测试 —— RESEARCH_PIPELINE §14。

预算停止不是自动成功：已有 Evidence 仍需通过完整度硬门槛；
达标 → partially_completed，否则 → failed（E3103，来源量不满足最小阈值）。
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


class TestBudgetStop:
    def setup_method(self):
        self.resolver = TaskStateResolver()

    def test_预算停止_证据达标_返回partially_completed(self):
        """§14：预算停止后已有 Evidence 通过完整度硬门槛 → partial（非自动成功）。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [
            _make_step("completed", step_type="planning"),
            _make_step("completed", step_type="search"),
            _make_step("completed", step_type="fetch"),
        ]
        # min_evidence = max(5, ceil(10*0.4)) = 5
        status, err = self.resolver.resolve(task, steps, evidence_count=6)
        assert status == "partially_completed"
        assert err is None

    def test_预算停止_证据不足_返回failed_E3103(self):
        """§14：预算停止且 Evidence 未达硬门槛 → failed（E3103，来源不足）。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [
            _make_step("completed", step_type="planning"),
            _make_step("completed", step_type="search"),
        ]
        status, err = self.resolver.resolve(task, steps, evidence_count=3)
        assert status == "failed"
        assert err is not None
        assert err["error_code"] == "E3103"
        assert err["recoverable"] is False

    def test_预算停止_边界证据刚好达标_返回partially_completed(self):
        """§17.2 边界：evidence == min_evidence 恰好达标。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(task, steps, evidence_count=5)
        assert status == "partially_completed"

    def test_预算停止_零证据_返回failed(self):
        """§17.2 规则 9：零 Evidence 不得利用空集合通过。"""
        task = _make_task(max_sources=10, budget_stopped_at=MagicMock())
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(task, steps, evidence_count=0)
        assert status == "failed"
        assert err["error_code"] == "E3103"

    def test_未预算停止_仍走正常运行守卫(self):
        """未触发预算停止时，phase 未全部尝试仍视为 running。"""
        task = _make_task(max_sources=10, budget_stopped_at=None)
        steps = [_make_step("completed", step_type="search")]
        status, err = self.resolver.resolve(task, steps, evidence_count=6)
        assert status == "running"
