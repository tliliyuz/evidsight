"""Refresh Token 模型。"""

from datetime import datetime
from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("refresh_token_families.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(256), nullable=False,
        comment="refresh_token 的 SHA-256 哈希，不存明文",
    )
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, server_default=text("NULL")
    )
    replaced_by_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, server_default=text("NULL"),
        comment="吊销时间（NULL=有效，非NULL=已吊销，UTC）",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp()
    )

    family = relationship("RefreshTokenFamily", back_populates="tokens", lazy="raise")
    replaced_by = relationship(
        "RefreshToken",
        remote_side="RefreshToken.id",
        foreign_keys=[replaced_by_id],
        lazy="raise",
        post_update=True,
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("idx_refresh_token_family", "family_id"),
    )
