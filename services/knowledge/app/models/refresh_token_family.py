"""Refresh Token Family 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class RefreshTokenFamily(Base):
    """一次登录会话及其全部 Refresh Token 的撤销边界。"""

    __tablename__ = "refresh_token_families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.platform_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, server_default=text("NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, server_default=text("NULL")
    )
    revoke_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True, server_default=text("NULL")
    )

    tokens = relationship(
        "RefreshToken",
        back_populates="family",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    __table_args__ = (
        Index("idx_refresh_family_user_active", "user_id", "revoked_at", "expires_at"),
    )
