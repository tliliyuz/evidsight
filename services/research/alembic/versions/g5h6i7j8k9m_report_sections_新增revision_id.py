"""report_sections 目标态归属：新增 revision_id 列与索引

Revision ID: g5h6i7j8k9m
Revises: g4h5i6j7k8l
Create Date: 2026-08-07

对齐 DATABASE.md §7.3 / ADR-009：report_sections 归属 Revision；
迁移态存量数据 revision_id 为空（task 级兼容），新发布链路写入 revision 归属。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "g5h6i7j8k9m"
down_revision: str | None = "g4h5i6j7k8l"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_sections",
        sa.Column("revision_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_report_section_revision",
        "report_sections",
        "report_revisions",
        ["revision_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_report_section_revision", "report_sections", ["revision_id"])


def downgrade() -> None:
    op.drop_constraint("fk_report_section_revision", "report_sections", type_="foreignkey")
    op.drop_index("idx_report_section_revision", table_name="report_sections")
    op.drop_column("report_sections", "revision_id")
