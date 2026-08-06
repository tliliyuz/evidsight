"""research_tasks 新增预算冻结/结算列

Revision ID: f3g4h5i6j7k
Revises: e2f3a4b5c6d
Create Date: 2026-08-06

对齐 DATABASE.md §5.1 与 RESEARCH_PIPELINE §14：
- budget_frozen：冻结上限快照（schema_version + 各维度上限），创建时服务端默认推导；
- budget_usage：结算用量（schema_version + 各维度实际用量），随外部调用累加；
- budget_stopped_at：预算停止时间；预算停止不是自动成功，终态由 Resolver 按证据硬门槛推导。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f3g4h5i6j7k"
down_revision: str | None = "e2f3a4b5c6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column("budget_frozen", sa.JSON(), nullable=True),
    )
    op.add_column(
        "research_tasks",
        sa.Column("budget_usage", sa.JSON(), nullable=True),
    )
    op.add_column(
        "research_tasks",
        sa.Column("budget_stopped_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "budget_stopped_at")
    op.drop_column("research_tasks", "budget_usage")
    op.drop_column("research_tasks", "budget_frozen")
