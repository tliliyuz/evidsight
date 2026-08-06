"""evidence_items 新增来源分型与内部稳定身份列

Revision ID: c0d1e2f3a4b5
Revises: a5b6c7d8e9f0
Create Date: 2026-08-06

对齐 DATABASE.md §6.2：
- 新增 `source_type`（internal|web，默认 web，存量回填 web）；
- 新增内部稳定身份列（knowledge_base_id/document_id/document_version_id/segment_id）
  与显示快照（document_display_name_snapshot）、共同字段（display_title、
  location_summary、source_observed_at、score_summary、validity）；
- 新增 Web 快照列（canonical_url_snapshot、fetched_at_snapshot）；
- `content`/`source_id` 改为可空：internal 证据无正文、不引用 Web source；
- 新增内部唯一键 `uq_evidence_internal_identity`（task_id + 四段内部稳定 ID）。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column(
            "source_type",
            sa.Enum("internal", "web", name="evidence_source_type"),
            server_default=sa.text("'web'"),
            nullable=False,
            comment="来源类型：internal / web（DATABASE.md §6.2）",
        ),
    )

    # ── Web 快照（对齐 EvidenceReference WebSourceIdentity）──
    op.add_column(
        "evidence_items",
        sa.Column(
            "canonical_url_snapshot",
            sa.String(2048),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "fetched_at_snapshot",
            sa.DateTime(timezone=True),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )

    # ── Internal 稳定身份（source_type=internal 时使用）──
    op.add_column(
        "evidence_items",
        sa.Column("knowledge_base_id", sa.String(36), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column("document_id", sa.String(36), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column("document_version_id", sa.String(36), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column("segment_id", sa.String(36), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "document_display_name_snapshot",
            sa.String(500),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )

    # ── 共同字段 ──
    op.add_column(
        "evidence_items",
        sa.Column("display_title", sa.String(500), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "location_summary",
            sa.String(1000),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "source_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column("score_summary", sa.JSON(), server_default=sa.text("NULL"), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "validity",
            sa.Enum("available", "restricted", "missing", "stale", name="evidence_validity"),
            server_default=sa.text("'available'"),
            nullable=False,
            comment="来源有效性观察状态（DATABASE.md §6.2）",
        ),
    )

    # ── content / source_id 改为可空（internal 无正文、不引用 web source）──
    op.alter_column("evidence_items", "content", existing_type=sa.Text(), nullable=True)
    op.alter_column("evidence_items", "source_id", existing_type=sa.Integer(), nullable=True)

    # ── 内部唯一键（DATABASE.md §6.2 约束 4）──
    op.create_unique_constraint(
        "uq_evidence_internal_identity",
        "evidence_items",
        ["task_id", "knowledge_base_id", "document_id", "document_version_id", "segment_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_evidence_internal_identity", "evidence_items", type_="unique")
    op.alter_column("evidence_items", "source_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("evidence_items", "content", existing_type=sa.Text(), nullable=False)
    op.drop_column("evidence_items", "validity")
    op.drop_column("evidence_items", "score_summary")
    op.drop_column("evidence_items", "source_observed_at")
    op.drop_column("evidence_items", "location_summary")
    op.drop_column("evidence_items", "display_title")
    op.drop_column("evidence_items", "document_display_name_snapshot")
    op.drop_column("evidence_items", "segment_id")
    op.drop_column("evidence_items", "document_version_id")
    op.drop_column("evidence_items", "document_id")
    op.drop_column("evidence_items", "knowledge_base_id")
    op.drop_column("evidence_items", "fetched_at_snapshot")
    op.drop_column("evidence_items", "canonical_url_snapshot")
    op.drop_column("evidence_items", "source_type")
