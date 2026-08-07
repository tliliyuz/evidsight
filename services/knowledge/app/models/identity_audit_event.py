"""身份安全审计事件模型。"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Enum, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._types import UTCDateTime


class IdentityAuditEvent(Base):
    """不含凭证与正文的身份安全事件摘要。"""

    __tablename__ = "identity_audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(
        Enum("success", "denied", "error", name="identity_audit_outcome"),
        nullable=False,
    )
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint("event_uuid", name="uq_identity_audit_event_uuid"),
        Index("idx_identity_audit_user_created", "user_id", "created_at"),
        Index("idx_identity_audit_request_id", "request_id"),
    )
