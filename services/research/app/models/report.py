"""
报告根表 ORM 模型 —— reports 表。

对齐 DATABASE.md §7.1 目标态：
- 每个 Task 最多一个报告根，task_id 唯一并级联删除；
- current_revision_id 指向同一 Report 的 published Revision（延迟 FK，避免循环外键）；
- 先创建 Report，再创建 Revision，发布事务最后设置 current_revision_id。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid


class Report(Base):
    """报告根表 —— 每个研究任务至多一个报告。"""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="唯一归属 Task，级联删除",
    )
    current_revision_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        sa.ForeignKey("report_revisions.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="当前已发布 Revision（发布事务切换）",
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

    task = relationship("ResearchTask", back_populates="report")
    revisions = relationship(
        "ReportRevision",
        back_populates="report",
        foreign_keys="ReportRevision.report_id",
        cascade="all, delete-orphan",
    )
    current_revision = relationship(
        "ReportRevision", foreign_keys=[current_revision_id], post_update=True
    )

    def __repr__(self):
        return f"<Report(id={self.id}, task_id={self.task_id})>"
