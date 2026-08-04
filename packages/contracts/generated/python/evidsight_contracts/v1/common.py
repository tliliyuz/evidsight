"""由 packages/contracts/schemas/v1/common.schema.json 生成，请勿手工编辑业务字段。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# SemVer：^\d+\.\d+\.\d+(-[\w\.]+)?(\+[\w\.]+)?$
SemVerStr = str

# UUIDv4：format=uuid
PlatformUserId = str
KnowledgeBaseId = str
DocumentId = str
DocumentVersionId = str
SegmentId = str
EvidenceId = str
ClaimId = str
RelationId = str
HitId = str

# NonNegativeInteger：minimum=0
NonNegativeInt = int

# NonEmptyString：minLength=1
NonEmptyStr = str

# RequestId：minLength=1
RequestId = str

# Timestamp：RFC3339 UTC（Z 结尾），^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$
Timestamp = str

# UnitInterval：0—1 闭区间
UnitInterval = float

# ScoreKind：vector / bm25 / rrf / coarse / rerank
ScoreKind = Literal["vector", "bm25", "rrf", "coarse", "rerank"]


class CharSpan(BaseModel):
    """字符区间；start 必须小于 end。"""

    model_config = ConfigDict(extra="forbid")

    start: NonNegativeInt = Field(ge=0, description="字符区间起点（含）。")
    end: NonNegativeInt = Field(ge=0, description="字符区间终点（不含）。")


class SourceLocation(BaseModel):
    """来源可解释定位：页码、章节路径或字符区间中的至少一种。"""

    model_config = ConfigDict(extra="forbid")

    page_number: NonNegativeInt | None = Field(default=None, ge=0, description="来源页码。")
    section_path: list[NonEmptyStr] | None = Field(default=None, description="章节路径。")
    char_span: CharSpan | None = Field(default=None, description="字符区间。")

    @model_validator(mode="after")
    def _at_least_one_option(self):
        if self.page_number is None and self.section_path is None and self.char_span is None:
            raise ValueError("location 必须包含页码、章节路径或字符区间中的至少一种")
        return self


class InternalSourceIdentity(BaseModel):
    """内部来源稳定身份：KB、Document、Document Version 与 Segment 的稳定 UUID。"""

    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: KnowledgeBaseId = Field(description="目标 Knowledge Base 的稳定 ID。")
    document_id: DocumentId = Field(description="文档的稳定 ID。")
    document_version_id: DocumentVersionId = Field(description="文档版本的稳定 ID。")
    segment_id: SegmentId = Field(description="Segment（Chunk）的稳定 ID。")


def require_unique_items(items, label: str):
    """对应 Schema 的 uniqueItems 约束；BaseModel 实例按 model_dump 去重。"""
    keys = []
    for item in items:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        keys.append(tuple(sorted(item.items())) if isinstance(item, dict) else item)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} 必须去重")
    return items
