"""
章节-证据关联表 ORM 模型 —— section_evidence 表。

表结构严格遵循 [DATABASE.md §2](docs/DATABASE.md#2-表结构)。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SectionEvidence(Base):
    """章节-证据关联表 —— M:N 关联表。联合主键防止重复关联。"""

    __tablename__ = "section_evidence"

    section_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("report_sections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self):
        return f"<SectionEvidence(section={self.section_id}, evidence={self.evidence_id})>"
