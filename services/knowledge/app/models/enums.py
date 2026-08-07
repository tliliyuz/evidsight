"""共享枚举 — DocumentStatus 统一管理，前后端共用定义来源

对齐 ADR-007 / RAG_PIPELINE.md §3：对外 Document 状态固定为
queued | processing | completed | partial | failed | deleting。
内部 Version 阶段名（parsing/chunking/embedding/indexing/verifying）不得
直接作为 DocumentStatus 泄漏，统一由 app/ingest/versioning.map_document_status
映射为 processing。
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """文档入库状态（对齐 API.md §6.2 与 ADR-007 对外映射）"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    DELETING = "deleting"


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        DocumentStatus.COMPLETED,
        DocumentStatus.PARTIAL,
        DocumentStatus.FAILED,
    }
)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
