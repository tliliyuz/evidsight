"""目标态报告数据层：evidence/report 对外 UUID + reports/report_revisions/claims/evidence_relations 表

Revision ID: g4h5i6j7k8l
Revises: f3g4h5i6j7k
Create Date: 2026-08-07

对齐 DATABASE.md §7 / ADR-009（用户 2026-08-07 裁决走目标态数据层方案）：
- evidence_items / report_sections 新增 external_id（对外稳定 UUID，存量回填）；
- 新建 reports：task_id 唯一并级联删除，current_revision_id 延迟 FK 指向 published Revision；
- 新建 report_revisions：(report_id, revision_number) 唯一，status 状态机 + 完整度摘要；
- 新建 claims：revision/section FK，sequence + certainty/qualification；
- 新建 evidence_relations：(claim_id, evidence_id, relation_type) 唯一，confidence 0-1。
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision: str = "g4h5i6j7k8l"
down_revision: str | None = "f3g4h5i6j7k"
branch_labels = None
depends_on = None


def _backfill_external_ids(table_name: str) -> None:
    """为存量行回填对外 UUID（external_id），使用 MySQL UUID() 函数避免应用侧回填。"""
    op.execute(
        sa.text(f"UPDATE {table_name} SET external_id = UUID() WHERE external_id = '' OR external_id IS NULL")
    )


def upgrade() -> None:
    # 1. 既有表加对外 UUID
    op.add_column(
        "evidence_items",
        sa.Column("external_id", sa.String(36), server_default="", nullable=False),
    )
    op.add_column(
        "report_sections",
        sa.Column("external_id", sa.String(36), server_default="", nullable=False),
    )
    _backfill_external_ids("evidence_items")
    _backfill_external_ids("report_sections")
    op.alter_column("evidence_items", "external_id", existing_type=sa.String(36), server_default=None, nullable=False)
    op.alter_column("report_sections", "external_id", existing_type=sa.String(36), server_default=None, nullable=False)
    op.create_unique_constraint("uq_evidence_external_id", "evidence_items", ["external_id"])
    op.create_unique_constraint("uq_report_section_external_id", "report_sections", ["external_id"])

    # 2. reports
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("current_revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    # 3. report_revisions（先建，供 reports.current_revision_id 延迟 FK）
    op.create_table(
        "report_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("building", "published", "failed", name="report_revision_status"), nullable=False),
        sa.Column(
            "build_step_id",
            sa.String(36),
            sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("based_on_revision_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("executive_summary", MEDIUMTEXT(), nullable=True),
        sa.Column("language", sa.String(10), server_default="zh", nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("evidence_completeness", sa.JSON(), nullable=True),
        sa.Column("limitations_summary", MEDIUMTEXT(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_summary", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("report_id", "revision_number", name="uq_report_revision_number"),
        sa.Index("idx_report_status", "report_id", "status"),
    )

    # reports.current_revision_id 延迟 FK（避免循环外键）
    op.create_foreign_key(
        "fk_reports_current_revision",
        "reports",
        "report_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. claims
    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("report_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            sa.Integer(),
            sa.ForeignKey("report_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("statement", MEDIUMTEXT(), nullable=False),
        sa.Column("certainty", sa.Enum("high", "medium", "low", name="claim_certainty"), nullable=False),
        sa.Column("qualification", MEDIUMTEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Index("idx_claim_revision_section", "revision_id", "section_id", "sequence"),
    )

    # 5. evidence_relations
    op.create_table(
        "evidence_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relation_type",
            sa.Enum("supports", "contradicts", "context", name="evidence_relation_type"),
            nullable=False,
        ),
        sa.Column("confidence", sa.DECIMAL(4, 3), nullable=False),
        sa.Column("rationale_summary", sa.String(1000), nullable=True),
        sa.Column(
            "created_by_step_id",
            sa.String(36),
            sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("claim_id", "evidence_id", "relation_type", name="uq_claim_evidence_relation"),
        sa.Index("idx_evidence_relation", "evidence_id", "relation_type"),
    )


def downgrade() -> None:
    op.drop_table("evidence_relations")
    op.drop_table("claims")
    op.drop_constraint("fk_reports_current_revision", "reports", type_="foreignkey")
    op.drop_table("report_revisions")
    op.drop_table("reports")
    op.drop_constraint("uq_report_section_external_id", "report_sections", type_="unique")
    op.drop_constraint("uq_evidence_external_id", "evidence_items", type_="unique")
    op.drop_column("report_sections", "external_id")
    op.drop_column("evidence_items", "external_id")
