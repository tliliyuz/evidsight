"""ORM 模型 — 导入所有模型确保 Alembic 能识别"""

from app.core.database import Base

from .chunk import Chunk
from .conversation import Conversation
from .document import Document
from .document_version import DocumentVersion
from .enums import TERMINAL_STATUSES, DocumentStatus, is_terminal  # noqa: F401
from .identity_audit_event import IdentityAuditEvent
from .knowledge_base import KnowledgeBase
from .message import Message
from .refresh_token import RefreshToken
from .refresh_token_family import RefreshTokenFamily
from .section import Section
from .trace import Trace
from .user import User

__all__ = [
    "Base",
    "DocumentStatus",
    "TERMINAL_STATUSES",
    "is_terminal",
    "User",
    "KnowledgeBase",
    "Document",
    "DocumentVersion",
    "Section",
    "Chunk",
    "Conversation",
    "Message",
    "IdentityAuditEvent",
    "RefreshTokenFamily",
    "RefreshToken",
    "Trace",
]
