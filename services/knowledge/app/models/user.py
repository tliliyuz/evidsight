"""用户表"""

from datetime import datetime
import uuid

from sqlalchemy import BigInteger, Enum, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._types import UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform_user_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("user", "admin", name="user_role"),
        default="user",
        server_default=text("'user'"),
    )
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled", name="user_status"),
        default="active",
        server_default=text("'active'"),
    )
    status_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # lazy="raise"：禁止隐式加载关联数据，需显式 selectinload()/joinedload()
    # 避免 get_current_user() 仅检查 status 时意外加载全部关联记录
    knowledge_bases = relationship(
        "KnowledgeBase", back_populates="owner", lazy="raise",
    )
    conversations = relationship(
        "Conversation", back_populates="user", passive_deletes=True,
        lazy="raise",
    )
