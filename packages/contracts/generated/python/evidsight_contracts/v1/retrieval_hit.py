"""由 packages/contracts/schemas/v1/retrieval-hit.schema.json 生成，请勿手工编辑业务字段。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import (
    DocumentId,
    DocumentVersionId,
    HitId,
    KnowledgeBaseId,
    NonEmptyStr,
    NonNegativeInt,
    ScoreKind,
    SegmentId,
    SourceLocation,
    Timestamp,
)


class RetrievalScore(BaseModel):
    """带 score_kind、value 和排序位置的受控分数。"""

    model_config = ConfigDict(extra="forbid")

    score_kind: ScoreKind
    value: float
    rank: NonNegativeInt = Field(ge=0, description="该分数来源阶段内的排序位置。")


class RetrievalHit(BaseModel):
    """Internal Retrieval 的临时命中对象；minimal_excerpt 不得持久化或进入日志/Trace/报告。"""

    model_config = ConfigDict(extra="forbid")

    hit_id: HitId
    knowledge_base_id: KnowledgeBaseId
    document_id: DocumentId
    document_version_id: DocumentVersionId
    segment_id: SegmentId
    document_display_name: NonEmptyStr
    section_title: NonEmptyStr | None = None
    location: SourceLocation
    minimal_excerpt: str = Field(min_length=1, max_length=8000)
    scores: list[RetrievalScore] = Field(min_length=1)
    source_updated_at: Timestamp
    retrieved_at: Timestamp
    access_scope: Literal["internal"]
