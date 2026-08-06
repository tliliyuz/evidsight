"""
证据条目表 ORM 模型 —— evidence_items 表。

表结构对齐 DATABASE.md §6.2（含迁移态）：
- `source_type` 为 `internal|web`，两类来源字段严格互斥；
- Internal 只持久化稳定 KB/Document/Document Version/Segment ID、显示快照、
  位置、时间与评分摘要，不提供任何正文列（content 恒为 NULL）；
- Web 仍为迁移态：source_id 指向 research_sources，正文可存 content
  （目标态为 web_sources + canonical_url_snapshot/fetched_at_snapshot，见 §2.2）。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime

# source_type 枚举（DATABASE.md §6.2）
EVIDENCE_SOURCE_TYPE_INTERNAL = "internal"
EVIDENCE_SOURCE_TYPE_WEB = "web"

# validity 枚举（DATABASE.md §6.2：观察状态，不是授权凭证）
EVIDENCE_VALIDITY_AVAILABLE = "available"
EVIDENCE_VALIDITY_RESTRICTED = "restricted"
EVIDENCE_VALIDITY_MISSING = "missing"
EVIDENCE_VALIDITY_STALE = "stale"


class EvidenceItem(Base):
    """证据条目表 —— EvidenceReference 的关系化持久表示。"""

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(
        sa.Integer, primary_key=True, autoincrement=True,
    )
    task_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── 来源分型（DATABASE.md §6.2）──
    source_type: Mapped[str] = mapped_column(
        sa.Enum(EVIDENCE_SOURCE_TYPE_INTERNAL, EVIDENCE_SOURCE_TYPE_WEB,
                name="evidence_source_type"),
        default=EVIDENCE_SOURCE_TYPE_WEB,
        server_default=sa.text("'web'"),
        nullable=False,
        comment="来源类型：internal / web",
    )

    # ── Web 来源（迁移态：仍指向 research_sources；目标态见 DATABASE.md §6.1/§6.2）──
    source_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("research_sources.id", ondelete="CASCADE"),
        nullable=True,
        comment="Web 来源 id（source_type=web 时使用；internal 时为空）",
    )
    canonical_url_snapshot: Mapped[str | None] = mapped_column(
        sa.String(2048), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="Web canonical URL 快照（对齐 EvidenceReference）",
    )
    fetched_at_snapshot: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, default=None, server_default=sa.text("NULL"),
        comment="Web 抓取时间快照（对齐 EvidenceReference）",
    )

    # ── Internal 稳定身份（source_type=internal 时使用）──
    knowledge_base_id: Mapped[str | None] = mapped_column(
        sa.String(36), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="Knowledge Base 稳定 UUID（无跨库 FK）",
    )
    document_id: Mapped[str | None] = mapped_column(
        sa.String(36), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="文档稳定 UUID",
    )
    document_version_id: Mapped[str | None] = mapped_column(
        sa.String(36), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="文档版本稳定 UUID（重处理后历史来源身份）",
    )
    segment_id: Mapped[str | None] = mapped_column(
        sa.String(36), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="Segment（Chunk）稳定 UUID",
    )
    document_display_name_snapshot: Mapped[str | None] = mapped_column(
        sa.String(500), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="内部文档显示名快照，仅展示，不授予原文访问权",
    )

    # ── 共同字段（DATABASE.md §6.2 / EvidenceReference）──
    display_title: Mapped[str | None] = mapped_column(
        sa.String(500), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="可公开的标题摘要",
    )
    location_summary: Mapped[str | None] = mapped_column(
        sa.String(1000), nullable=True, default=None, server_default=sa.text("NULL"),
        comment="可公开的位置摘要（页码/章节路径），不含内部路径",
    )
    source_observed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, default=None, server_default=sa.text("NULL"),
        comment="检索或抓取时观察到的来源时间",
    )
    score_summary: Mapped[dict | None] = mapped_column(
        sa.JSON, nullable=True, default=None, server_default=sa.text("NULL"),
        comment='{"best_score","score_kind","rank"} 受控评分摘要，非当前权限证明',
    )
    validity: Mapped[str] = mapped_column(
        sa.Enum(EVIDENCE_VALIDITY_AVAILABLE, EVIDENCE_VALIDITY_RESTRICTED,
                EVIDENCE_VALIDITY_MISSING, EVIDENCE_VALIDITY_STALE,
                name="evidence_validity"),
        default=EVIDENCE_VALIDITY_AVAILABLE,
        server_default=sa.text("'available'"),
        nullable=False,
        comment="来源有效性观察状态",
    )

    step_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
        default=None,
        server_default=sa.text("NULL"),
        comment="产生此证据的 Step（NULL = 非 Step 产生）",
    )

    # 内部证据禁止正文；web 迁移态正文存于此（目标态移除）
    content: Mapped[str | None] = mapped_column(
        sa.Text, nullable=True, default=None, server_default=sa.text("NULL"),
        comment="（迁移态）Web 证据正文片段；internal 证据恒为 NULL",
    )
    relevance_score: Mapped[float | None] = mapped_column(
        sa.DECIMAL(4, 3), default=None, server_default=sa.text("NULL"),
        comment="Rerank 相关性分数 (0.000-1.000)",
    )

    # ── 用于哪些章节 ──
    used_in_sections: Mapped[dict | None] = mapped_column(
        sa.JSON, default=None, server_default=sa.text("NULL"),
        comment='如 ["1", "2.1"]',
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    # ── 索引 ──
    __table_args__ = (
        sa.Index("idx_task", "task_id"),
        sa.Index("idx_source", "source_id"),
        sa.Index("idx_score", "task_id", sa.text("relevance_score DESC")),
        # DATABASE.md §6.2 约束 4：内部唯一键 (task_id, kb, doc, version, segment)；
        # MySQL unique index 允许多个 NULL，web 行（内部 ID 全 NULL）不受影响。
        sa.UniqueConstraint(
            "task_id", "knowledge_base_id", "document_id",
            "document_version_id", "segment_id",
            name="uq_evidence_internal_identity",
        ),
    )

    # ── 关联 ──
    task = relationship("ResearchTask", back_populates="evidence_items")
    source = relationship("ResearchSource", back_populates="evidence_items")
    step = relationship("ResearchStep", back_populates="evidence_items")
    sections = relationship(
        "ReportSection",
        secondary="section_evidence",
        back_populates="evidence_items",
    )

    def __repr__(self):
        return f"<EvidenceItem(id={self.id}, task_id={self.task_id}, type={self.source_type})>"
