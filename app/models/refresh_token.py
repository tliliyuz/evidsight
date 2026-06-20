"""
刷新令牌表 ORM 模型 —— refresh_tokens 表。

表结构严格遵循 [DATABASE.md §2](docs/DATABASE.md#2-表结构)。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class RefreshToken(Base):
    """刷新令牌表 —— SHA-256 哈希存储，支持 Rotation 与泄露检测。"""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(
        sa.BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        sa.String(256),
        nullable=False,
        comment="refresh_token 的 SHA-256 哈希，不存明文",
    )
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        comment="过期时间（创建后 7 天）",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        default=None,
        server_default=sa.text("NULL"),
        comment="吊销时间（NULL=有效，非NULL=已吊销）",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp()
    )

    # ── 索引 ──
    __table_args__ = (
        sa.Index("idx_user_id", "user_id"),
        sa.Index("idx_token_hash", "token_hash"),
        sa.Index("idx_user_active", "user_id", "revoked_at", "expires_at"),
    )

    # ── 关联 ──
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id})>"
