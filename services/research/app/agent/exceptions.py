"""Agent Runtime 层异常。"""


class AgentLoopExhaustedError(Exception):
    """Agent Loop 达到最大迭代次数仍未结束。"""

    def __init__(self, max_iterations: int):
        self.max_iterations = max_iterations
        super().__init__(f"Agent Loop 迭代次数超过上限 {max_iterations}")


class LeaseLostError(Exception):
    """Worker 失去任务租约，立即停止且不提交业务结果（§13.1 / §17.12）。

    由 Recovery Scanner 在租约过期后接管任务；失去租约的 Worker 不写任何
    业务结果，也不写终态，避免覆盖恢复 Worker 的完成事实。
    """

    def __init__(self, message: str = "Worker 已失去任务租约"):
        super().__init__(message)


class BudgetExhaustedError(Exception):
    """任务预算停止，停止发起新的外部调用（RESEARCH_PIPELINE §14）。

    预算停止不是自动成功：已有 Evidence 仍需通过完整度硬门槛，
    终态由 TaskStateResolver 推导 partial/failed。
    """

    def __init__(self, message: str = "任务预算已用尽，停止新调用"):
        super().__init__(message)
