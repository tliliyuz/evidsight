"""对齐 documents.status 枚举为 6 值 — ADR-007 / API.md §6.2 完整迁移

存量 10 值 ENUM（uploaded|parsing|chunking|embedding|vector_storing|
completed|success_with_warnings|partial_failed|failed|deleting）→ 新 6 值
（queued|processing|completed|partial|failed|deleting）。对外状态由
app.models.enums.DocumentStatus 输出，本迁移保证 DB 存储与模型一致。

映射规则（对齐 RAG_PIPELINE.md §3.3 的 map_document_status）：
- 有版本记录的文档按最新版本状态映射：ready→completed、
  ready_with_warnings→partial、failed→failed、queued→queued（f0a1b2c3d4e5
  已为每文档建立 version 1，含 queued/failed 等无 active_version 的文档，
  必须按版本而非 active_version 判定，避免 queued 版本文档误标 processing）
- 无版本记录的兜底近似映射：uploaded→queued、parsing/chunking/embedding/
  vector_storing→processing、success_with_warnings/partial_failed→partial

MySQL 对 ENUM 的限制要求先扩展（新旧值共存）→ UPDATE 映射 → 再收窄，
否则写入新枚举值会触发 Data truncated。downgrade 为近似映射（processing
无法区分原五个处理阶段），数据迁移固有的不可逆性在 DATABASE.md 注明。

Revision ID: c6d7e8f9a0b1
Revises: f0a1b2c3d4e5
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 旧 ENUM 值（04b3e0425da8 / 42097bdbd61a 定义）
_OLD_ENUM = (
    "'uploaded','parsing','chunking','embedding','vector_storing',"
    "'completed','success_with_warnings','partial_failed','failed','deleting'"
)
# 新旧共存（扩展用）
_FULL_ENUM = (
    "'uploaded','parsing','chunking','embedding','vector_storing','completed',"
    "'success_with_warnings','partial_failed','failed','deleting',"
    "'queued','processing','partial'"
)
# 新 6 值（收窄后）
_NEW_ENUM = "'queued','processing','completed','partial','failed','deleting'"


def upgrade() -> None:
    # 1. 扩展 ENUM：新旧值共存，才能写入新枚举值
    op.execute(
        f"ALTER TABLE documents MODIFY COLUMN status "
        f"ENUM({_FULL_ENUM}) NOT NULL DEFAULT 'uploaded'"
    )
    # 2. 按最新版本状态精确映射 documents.status（f0a1b2c3d4e5 已为每文档建立
    #    version 1，含 queued/failed 等无 active_version 的文档；有版本记录的
    #    一律以版本状态为准，避免把 queued 版本文档误标为 processing）
    op.execute(
        """
        UPDATE documents d
        LEFT JOIN document_versions v
          ON v.id = (
            SELECT v2.id FROM document_versions v2
            WHERE v2.document_id = d.id
            ORDER BY v2.version DESC
            LIMIT 1
          )
        SET d.status = CASE
          WHEN v.status IS NULL THEN
            CASE d.status
              WHEN 'uploaded' THEN 'queued'
              WHEN 'parsing' THEN 'processing'
              WHEN 'chunking' THEN 'processing'
              WHEN 'embedding' THEN 'processing'
              WHEN 'vector_storing' THEN 'processing'
              WHEN 'success_with_warnings' THEN 'partial'
              WHEN 'partial_failed' THEN 'partial'
              ELSE d.status END
          ELSE
            CASE v.status
              WHEN 'ready' THEN 'completed'
              WHEN 'ready_with_warnings' THEN 'partial'
              WHEN 'failed' THEN 'failed'
              WHEN 'queued' THEN 'queued'
              ELSE d.status END
        END
        """
    )
    # 3. 收窄 ENUM 到新 6 值，默认 queued
    op.execute(
        f"ALTER TABLE documents MODIFY COLUMN status "
        f"ENUM({_NEW_ENUM}) NOT NULL DEFAULT 'queued'"
    )


def downgrade() -> None:
    """近似映射回旧 10 值枚举（processing 无法区分原处理阶段，归入 parsing）。"""
    # 1. 扩展 ENUM 含新旧值
    op.execute(
        f"ALTER TABLE documents MODIFY COLUMN status "
        f"ENUM({_FULL_ENUM}) NOT NULL DEFAULT 'uploaded'"
    )
    # 2. 新值 → 旧值（近似）
    op.execute("UPDATE documents SET status='uploaded' WHERE status='queued'")
    op.execute("UPDATE documents SET status='parsing' WHERE status='processing'")
    op.execute(
        "UPDATE documents SET status='success_with_warnings' WHERE status='partial'"
    )
    # 3. 收窄回旧 10 值
    op.execute(
        f"ALTER TABLE documents MODIFY COLUMN status "
        f"ENUM({_OLD_ENUM}) NOT NULL DEFAULT 'uploaded'"
    )
