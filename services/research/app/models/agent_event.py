"""Agent Event —— 追加式业务执行审计表（DATABASE.md §5.4）。

agent_events 是追加式业务执行审计与 SSE 持久游标，不是 Chain-of-Thought 或
通用事件源。事件只含安全业务摘要（计数、稳定 ID、策略结果和公开错误码），
禁止 thought/reasoning/完整 Prompt/内部正文/凭证与堆栈。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid


class AgentEvent(Base):
    """Agent Event —— 单条业务执行审计事件，`(task_id, sequence)` 唯一。"""

    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
        default=None,
        server_default=sa.text("NULL"),
        comment="关联 ResearchStep.id；可空",
    )

    sequence: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="Task 内单调序号，SSE 持久游标",
    )
    event_type: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        comment="阶段进入/Tool 请求/Tool 结果/重试/预算停止/恢复等白名单枚举",
    )
    tool_name: Mapped[str | None] = mapped_column(
        sa.String(100),
        default=None,
        server_default=sa.text("NULL"),
        comment="受控 Tool 标识，可空",
    )
    provider_name: Mapped[str | None] = mapped_column(
        sa.String(100),
        default=None,
        server_default=sa.text("NULL"),
        comment="受控 Provider/模型标识，可空",
    )
    input_summary: Mapped[dict | None] = mapped_column(
        sa.JSON,
        default=None,
        server_default=sa.text("NULL"),
        comment="Schema 化安全摘要：计数、稳定 ID、策略结果、公开错误码",
    )
    result_summary: Mapped[dict | None] = mapped_column(
        sa.JSON,
        default=None,
        server_default=sa.text("NULL"),
        comment="Schema 化安全摘要：计数、稳定 ID、策略结果、公开错误码",
    )
    request_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        default=None,
        server_default=sa.text("NULL"),
        comment="调用链关联，不含凭证",
    )
    trace_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        default=None,
        server_default=sa.text("NULL"),
        comment="调用链关联，不含凭证",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        sa.Integer,
        default=None,
        server_default=sa.text("NULL"),
        comment="事件耗时（毫秒），观测字段",
    )
    cost_summary: Mapped[dict | None] = mapped_column(
        sa.JSON,
        default=None,
        server_default=sa.text("NULL"),
        comment="估算成本摘要，观测字段",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("task_id", "sequence", name="uq_agent_events_task_sequence"),
        sa.Index("idx_agent_events_task_created", "task_id", "created_at"),
    )

    task = relationship("ResearchTask", back_populates="agent_events")
    step = relationship("ResearchStep", back_populates="agent_events")

    def __repr__(self):
        return (
            f"<AgentEvent(id={self.id}, task_id={self.task_id}, "
            f"sequence={self.sequence}, event_type={self.event_type})>"
        )
