"""文档请求/响应模型"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus


class DocumentResponse(BaseModel):
    """文档响应（列表 & 详情共用）"""

    uuid: str
    kb_uuid: str
    filename: str
    file_type: str
    file_size: int | None = None
    status: DocumentStatus
    chunk_count: int = 0
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """文档列表分页数据"""

    total: int
    page: int
    page_size: int
    items: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    """文档上传响应数据"""

    uuid: str
    kb_uuid: str
    filename: str
    file_type: str
    file_size: int | None = None
    status: DocumentStatus

    model_config = {"from_attributes": True}


class DocumentDeleteResponse(BaseModel):
    """文档删除响应数据"""

    doc_uuid: str
    status: DocumentStatus


class DocumentReprocessResponse(BaseModel):
    """文档重新处理响应数据"""

    doc_uuid: str
    status: DocumentStatus


class DocumentBatchUploadItem(BaseModel):
    """批量上传 — 单个成功项"""

    uuid: str
    filename: str
    status: DocumentStatus


class DocumentBatchUploadFailedItem(BaseModel):
    """批量上传 — 单个失败项"""

    filename: str
    reason: str


class DocumentBatchUploadResponse(BaseModel):
    """批量上传响应数据"""

    success: list[DocumentBatchUploadItem]
    failed: list[DocumentBatchUploadFailedItem]


class DocumentChunkResponse(BaseModel):
    """文档分块响应"""

    # 内部整数 PK 仅迁移期兼容保留，不作为前端契约；稳定身份使用 segment_id
    id: int
    segment_id: str = Field(
        description="Segment 稳定 UUID（chunk.segment_uuid，即 v1 location API 的 location_id）"
    )
    chunk_index: int
    preview: str = Field(description="分块内容预览（默认截断至 200 字符）")
    token_count: int = 0
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class DocumentChunkListResponse(BaseModel):
    """文档分块列表分页数据"""

    total: int
    page: int
    page_size: int
    items: list[DocumentChunkResponse]


class DocumentLocationResponse(BaseModel):
    """文档来源位置响应 — 最小片段和定位（对齐 API.md §6.2）。

    实时鉴权后返回；location 结构对齐 Contract SourceLocation
    （page_number | section_path），不包含存储或内部路径。
    """

    document_id: str = Field(description="文档稳定 UUID")
    segment_id: str = Field(description="Segment 稳定 UUID（即 location_id）")
    minimal_excerpt: str = Field(description="最小必要片段（临时内容，不持久化）")
    location: dict[str, Any] = Field(description="安全定位（page_number 或 section_path）")
    source_updated_at: datetime | None = Field(default=None, description="来源最后更新时间")
