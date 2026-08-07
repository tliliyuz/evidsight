"""文档版本表 — 每次入库/重处理创建独立版本，检索只读 Document Active Version

对齐 DATABASE.md §5.3 与 ADR-007：MySQL 为唯一权威状态源，以阶段 Checkpoint
为恢复点；非 Active Version 不参与检索；Worker 丢失后以 Version 状态恢复。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_doc_version"),
        Index("idx_document_versions_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, comment="对外标识 / Worker 幂等键"
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属文档",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="同一 Document 内递增且唯一",
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "queued",
            "parsing",
            "chunking",
            "embedding",
            "indexing",
            "verifying",
            "ready",
            "ready_with_warnings",
            "failed",
            name="document_version_status",
        ),
        default="queued",
        server_default=text("'queued'"),
        comment="queued → parsing → chunking → embedding → indexing → verifying → ready；任一分阶段不可恢复错误 → failed",
    )
    last_success_batch: Mapped[int | None] = mapped_column(
        Integer, comment="非负 Checkpoint，恢复点"
    )
    expected_segment_count: Mapped[int | None] = mapped_column(Integer)
    embedded_segment_count: Mapped[int | None] = mapped_column(Integer)
    indexed_segment_count: Mapped[int | None] = mapped_column(Integer)
    staging_artifact_key: Mapped[str | None] = mapped_column(
        String(512), comment="Embedding staging 内部存储键，不对外暴露"
    )
    warning_summary: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64), comment="安全错误码")
    error_summary: Mapped[str | None] = mapped_column(String(500), comment="安全摘要")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    document = relationship("Document", back_populates="versions")
    sections = relationship("Section", back_populates="document_version", passive_deletes=True)
    chunks = relationship("Chunk", back_populates="document_version", passive_deletes=True)
