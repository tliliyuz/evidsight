"""新增 agent_events 追加式业务审计表

Revision ID: e2f3a4b5c6d
Revises: d1e2f3a4b5c
Create Date: 2026-08-06

对齐 DATABASE.md §5.4 / §9 与 RESEARCH_PIPELINE §15：
- agent_events 是追加式业务执行审计与 SSE 持久游标，不是 Chain-of-Thought 或通用事件源；
- event_type 白名单枚举（阶段进入/Tool 请求/Tool 结果/重试/预算停止/恢复等）；
- `(task_id, sequence)` 唯一，作为 SSE 持久游标；
- 事件只含安全业务摘要（计数、稳定 ID、策略结果和公开错误码）。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d"
down_revision: str | None = "d1e2f3a4b5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("step_id", sa.String(36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("provider_name", sa.String(100), nullable=True),
        sa.Column("input_summary", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("cost_summary", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["research_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "sequence", name="uq_agent_events_task_sequence"
        ),
    )
    op.create_index(
        "idx_agent_events_task_created",
        "agent_events",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_events_task_created", table_name="agent_events")
    op.drop_table("agent_events")
