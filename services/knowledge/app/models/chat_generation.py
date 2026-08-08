"""Chat 生成生命周期事实表。"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class ChatGeneration(Base):
    __tablename__ = "chat_generations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    platform_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "running", "completed", "failed", "canceled", name="chat_generation_status"
        ),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    conversation = relationship("Conversation")

    __table_args__ = (
        Index("idx_chat_generations_status_updated", "status", "updated_at"),
        Index("idx_chat_generations_conversation_created", "conversation_id", "created_at"),
    )
