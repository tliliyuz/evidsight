"""由 packages/contracts/schemas/v1/evidence-resolve-response.schema.json 生成，请勿手工编辑业务字段。"""
from pydantic import BaseModel, ConfigDict, Field

from .common import (
    DocumentId,
    DocumentVersionId,
    KnowledgeBaseId,
    RequestId,
    SegmentId,
    SemVerStr,
    SourceLocation,
    Timestamp,
)


class ResolvedSource(BaseModel):
    """按请求顺序返回的已解析来源；正文只允许存在于当前 Step 内存。"""

    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: KnowledgeBaseId
    document_id: DocumentId
    document_version_id: DocumentVersionId
    segment_id: SegmentId
    minimal_excerpt: str = Field(min_length=1, max_length=8000)
    location: SourceLocation
    source_updated_at: Timestamp


class EvidenceResolveResponse(BaseModel):
    """Internal Evidence Resolve 的成功响应。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: SemVerStr
    request_id: RequestId = Field(description="回显跨服务请求关联 ID。")
    results: list[ResolvedSource] = Field(min_length=1)
