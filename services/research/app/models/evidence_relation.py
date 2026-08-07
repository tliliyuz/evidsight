"""
证据-结论关系表 ORM 模型 —— evidence_relations 表。

对齐 DATABASE.md §7.5 目标态：
- relation_type 固定 supports|contradicts|context；
- confidence 为 0—1，只代表关系判断信心，不代表来源绝对真实性；
- (claim_id, evidence_id, relation_type) 唯一，重复关系合并；
- rationale_summary 为安全摘要，不得复制内部正文。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid
from app.models.enums import EVIDENCE_RELATION_TYPE_ENUM

# 关系类型枚举（DATABASE.md §7.5）
EVIDENCE_RELATION_SUPPORTS = "supports"
EVIDENCE_RELATION_CONTRADICTS = "contradicts"
EVIDENCE_RELATION_CONTEXT = "context"


class EvidenceRelation(Base):
    """证据关系 —— 连接 Claim 与 Evidence。"""

    __tablename__ = "evidence_relations"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    claim_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        sa.Enum(*EVIDENCE_RELATION_TYPE_ENUM, name="evidence_relation_type"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        sa.DECIMAL(4, 3),
        nullable=False,
        comment="0—1 关系判断置信度，不代表来源绝对真实性",
    )
    rationale_summary: Mapped[str | None] = mapped_column(
        sa.String(1000),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="安全摘要，不得复制内部正文",
    )
    created_by_step_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="生成关系的 Step",
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    # ── 索引 ──
    __table_args__ = (
        sa.UniqueConstraint(
            "claim_id", "evidence_id", "relation_type", name="uq_claim_evidence_relation"
        ),
        sa.Index("idx_evidence_relation", "evidence_id", "relation_type"),
    )

    claim = relationship("Claim", back_populates="relations")
    evidence = relationship("EvidenceItem", back_populates="relations")

    def __repr__(self):
        return f"<EvidenceRelation(claim={self.claim_id}, ev={self.evidence_id}, type={self.relation_type})>"
