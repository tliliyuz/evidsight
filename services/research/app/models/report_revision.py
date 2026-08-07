"""
报告版本表 ORM 模型 —— report_revisions 表。

对齐 DATABASE.md §7.2 目标态：
- (report_id, revision_number) 唯一且从 1 递增；
- status 为 building|published|failed；published 后不可变；
- evidence_completeness 保存三分项与总分（JSON），不由 LLM 直接给出；
- 构建失败标记 failed，重试创建更高 revision number。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime, new_uuid
from app.models.enums import REPORT_REVISION_STATUS_ENUM

# 报告版本状态枚举（DATABASE.md §7.2）
REPORT_REVISION_STATUS_BUILDING = "building"
REPORT_REVISION_STATUS_PUBLISHED = "published"
REPORT_REVISION_STATUS_FAILED = "failed"


class ReportRevision(Base):
    """报告版本 —— 不可变发布单元。"""

    __tablename__ = "report_revisions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    report_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="从 1 递增的版本号，同报告内唯一",
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(*REPORT_REVISION_STATUS_ENUM, name="report_revision_status"),
        default=REPORT_REVISION_STATUS_BUILDING,
        server_default=sa.text("'building'"),
        nullable=False,
    )
    build_step_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        sa.ForeignKey("research_steps.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="构建此版本的 Step",
    )
    based_on_revision_id: Mapped[str | None] = mapped_column(
        sa.String(36),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="整份重生成的来源版本（P1 谱系）",
    )

    title: Mapped[str] = mapped_column(
        sa.String(500),
        nullable=False,
        comment="报告标题（published 后不可变）",
    )
    executive_summary: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="执行摘要（不含内部摘录）",
    )
    language: Mapped[str] = mapped_column(
        sa.String(10),
        default="zh",
        server_default=sa.text("'zh'"),
        nullable=False,
    )
    content_hash: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="正文内容哈希，防篡改/防重复发布",
    )
    evidence_completeness: Mapped[dict | None] = mapped_column(
        sa.JSON,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment='{"question_coverage","channel_success","claim_coverage","score","rule_version"}',
    )
    limitations_summary: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="缺失/冲突/时效风险披露",
    )

    error_code: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="构建失败错误码（安全摘要）",
    )
    error_summary: Mapped[str | None] = mapped_column(
        sa.String(1000),
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="构建失败安全摘要",
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="published 时间",
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        nullable=True,
        default=None,
        server_default=sa.text("NULL"),
        comment="failed 时间",
    )

    # ── 索引 ──
    __table_args__ = (
        sa.UniqueConstraint("report_id", "revision_number", name="uq_report_revision_number"),
        sa.Index("idx_report_status", "report_id", "status"),
    )

    report = relationship(
        "Report",
        back_populates="revisions",
        foreign_keys=[report_id],
    )
    sections = relationship(
        "ReportSection", back_populates="revision", cascade="all, delete-orphan"
    )
    claims = relationship("Claim", back_populates="revision", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ReportRevision(id={self.id}, report={self.report_id}, rev={self.revision_number}, status={self.status})>"
