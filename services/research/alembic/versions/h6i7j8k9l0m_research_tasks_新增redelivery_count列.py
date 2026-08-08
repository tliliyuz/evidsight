"""research_tasks 新增 pending 重投递计数列

Revision ID: h6i7j8k9l0m
Revises: g5h6i7j8k9m
Create Date: 2026-08-08

对齐 DATABASE.md §5.1 与 RESEARCH_PIPELINE §13.6：
- redelivery_count：pending 重投递次数，周期扫描条件递增且非负；
  超过 PENDING_REDELIVERY_MAX_RETRIES 后创建受控失败事实（E3118），
  由 TaskStateResolver 推导 failed 终态，扫描器不直接写终态。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "h6i7j8k9l0m"
down_revision: str | None = "g5h6i7j8k9m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column(
            "redelivery_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "redelivery_count")
