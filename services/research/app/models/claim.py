"""
报告结论表 ORM 模型 —— claims 表。

对齐 DATABASE.md §7.4 目标态：
- Claim 是报告中接受 Evidence 评估的最小结论单元；
- 属于 Section 所在 Revision（revision_id + section_id FK）；
- statement 是综合结论，不得复制内部原文；
- certainty 为受控枚举（high|medium|low），qualification 为限定表述。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid
from app.models.enums import CLAIM_CERTAINTY_ENUM

# 结论确定性枚举（DATABASE.md §7.4：受控枚举或范围值，由 Pipeline 定义）
CLAIM_CERTAINTY_HIGH = "high"
CLAIM_CERTAINTY_MEDIUM = "medium"
CLAIM_CERTAINTY_LOW = "low"


class Claim(Base):
    """报告结论 —— 最小结论单元。"""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    revision_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("report_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("report_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="章节内结论顺序",
    )
    statement: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="综合结论（不复制内部原文）",
    )
    certainty: Mapped[str] = mapped_column(
        sa.Enum(*CLAIM_CERTAINTY_ENUM, name="claim_certainty"),
        nullable=False,
        comment="结论确定性：high / medium / low",
    )
    qualification: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="限定、不确定性与时效风险表述",
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    # ── 索引 ──
    __table_args__ = (
        sa.Index("idx_claim_revision_section", "revision_id", "section_id", "sequence"),
    )

    revision = relationship("ReportRevision", back_populates="claims")
    section = relationship("ReportSection", back_populates="claims")
    relations = relationship(
        "EvidenceRelation", back_populates="claim", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Claim(id={self.id}, rev={self.revision_id}, seq={self.sequence})>"
