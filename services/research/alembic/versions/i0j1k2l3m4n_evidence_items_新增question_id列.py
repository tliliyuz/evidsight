"""evidence_items 新增 question_id 列（完整度真实口径）

Revision ID: i0j1k2l3m4n
Revises: h6i7j8k9l0m
Create Date: 2026-08-08

对齐 RESEARCH_PIPELINE §5.1（稳定结构）/ §10.1 / DATABASE.md §6.2（切片 6）：
- question_id：evidence 归属 Planning 问题的稳定 ID（q1…qN），
  用于 question_coverage 真实分子计算；可空（存量/非 Planning 归属证据为空）。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "i0j1k2l3m4n"
down_revision: str | None = "h6i7j8k9l0m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column(
            "question_id",
            sa.String(length=36),
            nullable=True,
            server_default=sa.text("NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "question_id")
