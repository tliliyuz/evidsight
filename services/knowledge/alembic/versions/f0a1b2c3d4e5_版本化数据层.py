"""版本化数据层 — document_versions 表 + 检索 Active Version 支撑列与存量回填

对齐 ADR-007 / DATABASE.md §5.3：每次入库/重处理创建独立版本，检索只读
Document Active Version。存量数据回填为版本 1：display_name=filename，
每个文档建立 version=1（状态由 documents.status 映射），可检索文档设置
active_version=1，chunk 回填稳定 segment_uuid 与 document_version_id，
section 回填 document_version_id。入库写路径的版本化在后续切片落地。

Revision ID: f0a1b2c3d4e5
Revises: e4f5a6b7c8e0
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. document_versions 建表（chunks/sections 的外键列后置，避免引用未建表）
    op.create_table(
        "document_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False, comment="对外标识 / Worker 幂等键"),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            comment="所属文档",
        ),
        sa.Column("version", sa.Integer(), nullable=False, comment="同一 Document 内递增且唯一"),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "parsing", "chunking", "embedding", "indexing", "verifying",
                "ready", "ready_with_warnings", "failed",
                name="document_version_status",
            ),
            nullable=False,
            server_default=sa.text("'queued'"),
            comment="queued → parsing → chunking → embedding → indexing → verifying → ready；任一分阶段不可恢复错误 → failed",
        ),
        sa.Column("last_success_batch", sa.Integer(), nullable=True, comment="非负 Checkpoint，恢复点"),
        sa.Column("expected_segment_count", sa.Integer(), nullable=True),
        sa.Column("embedded_segment_count", sa.Integer(), nullable=True),
        sa.Column("indexed_segment_count", sa.Integer(), nullable=True),
        sa.Column("staging_artifact_key", sa.String(512), nullable=True, comment="Embedding staging 内部存储键，不对外暴露"),
        sa.Column("warning_summary", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True, comment="安全错误码"),
        sa.Column("error_summary", sa.String(500), nullable=True, comment="安全摘要"),
        sa.Column("created_at", mysql.DATETIME(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("published_at", mysql.DATETIME(), nullable=True),
        sa.UniqueConstraint("document_id", "version", name="uq_document_versions_doc_version"),
        sa.UniqueConstraint("uuid", name="uq_document_versions_uuid"),
        sa.Index("ix_document_versions_document_id", "document_id"),
        sa.Index("idx_document_versions_status_updated", "status", "updated_at"),
    )

    # 2. knowledge_bases 新增索引状态列（存量行回填 ready / 0）
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "index_status",
            sa.Enum("ready", "updating", "recovering", name="kb_index_status"),
            nullable=False,
            server_default=sa.text("'ready'"),
            comment="ready（可检索）/ updating（版本发布中，新检索有界等待）/ recovering（索引恢复中）",
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "index_generation", sa.BigInteger(), nullable=False,
            server_default=sa.text("0"),
            comment="非负向量发布世代，发布时递增",
        ),
    )

    # 3. documents 新增 display_name / active_version
    op.add_column(
        "documents",
        sa.Column("display_name", sa.String(256), nullable=True, comment="用户可见名称；缺失时回退为 filename"),
    )
    op.add_column(
        "documents",
        sa.Column("active_version", sa.Integer(), nullable=True, comment="当前可检索版本号，可空；检索只读该版本"),
    )

    # 4. chunks 新增 segment_uuid / document_version_id
    op.add_column(
        "chunks",
        sa.Column("segment_uuid", sa.String(36), nullable=True,
                  comment="Evidence 稳定 Segment UUID；Internal Retrieval 以它返回位置"),
    )
    op.create_unique_constraint("uq_chunks_segment_uuid", "chunks", ["segment_uuid"])
    op.add_column(
        "chunks",
        sa.Column("document_version_id", sa.BigInteger(), nullable=True,
                  comment="所属 Document Version ID（迁移态允许空，版本化入库后必填）"),
    )
    op.create_foreign_key(
        "fk_chunks_document_version", "chunks", "document_versions",
        ["document_version_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_chunks_document_version_id", "chunks", ["document_version_id"])

    # 5. sections 新增 document_version_id
    op.add_column(
        "sections",
        sa.Column("document_version_id", sa.BigInteger(), nullable=True,
                  comment="所属 Document Version ID（迁移态允许空）"),
    )
    op.create_foreign_key(
        "fk_sections_document_version", "sections", "document_versions",
        ["document_version_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_sections_document_version_id", "sections", ["document_version_id"])

    # 6. 回填 display_name = filename
    op.execute(
        "UPDATE documents SET display_name = filename "
        "WHERE display_name IS NULL OR display_name = ''"
    )

    # 7. 每个文档建立版本 1（状态由文档状态映射），可检索文档设置 Active Version
    #    映射：completed→ready / success_with_warnings→ready_with_warnings /
    #          partial_failed→ready_with_warnings / failed→failed / 其余→queued
    op.execute(
        """
        INSERT INTO document_versions
            (uuid, document_id, version, status, published_at, created_at, updated_at)
        SELECT UUID(), d.id, 1,
               CASE d.status
                   WHEN 'completed' THEN 'ready'
                   WHEN 'success_with_warnings' THEN 'ready_with_warnings'
                   WHEN 'partial_failed' THEN 'ready_with_warnings'
                   WHEN 'failed' THEN 'failed'
                   ELSE 'queued'
               END,
               COALESCE(d.updated_at, d.created_at),
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM documents d
        WHERE NOT EXISTS (
            SELECT 1 FROM document_versions v WHERE v.document_id = d.id AND v.version = 1
        )
        """
    )
    op.execute(
        """
        UPDATE documents d
        JOIN document_versions v ON v.document_id = d.id AND v.version = 1
        SET d.active_version = 1
        WHERE v.status IN ('ready', 'ready_with_warnings')
        """
    )

    # 8. 回填 chunk 稳定 segment_uuid + document_version_id
    op.execute(
        """
        UPDATE chunks c
        JOIN document_versions v ON v.document_id = c.doc_id AND v.version = 1
        SET c.document_version_id = v.id,
            c.segment_uuid = COALESCE(c.segment_uuid, UUID())
        """
    )

    # 9. 回填 section document_version_id
    op.execute(
        """
        UPDATE sections s
        JOIN document_versions v ON v.document_id = s.doc_id AND v.version = 1
        SET s.document_version_id = v.id
        """
    )


def downgrade() -> None:
    # MySQL 要求先删外键约束再删列；单列索引随列自动删除。
    op.drop_constraint("fk_sections_document_version", "sections", type_="foreignkey")
    op.drop_column("sections", "document_version_id")

    op.drop_constraint("fk_chunks_document_version", "chunks", type_="foreignkey")
    op.drop_constraint("uq_chunks_segment_uuid", "chunks", type_="unique")
    op.drop_column("chunks", "document_version_id")
    op.drop_column("chunks", "segment_uuid")

    op.drop_column("documents", "active_version")
    op.drop_column("documents", "display_name")

    op.drop_column("knowledge_bases", "index_generation")
    op.drop_column("knowledge_bases", "index_status")

    op.drop_table("document_versions")
