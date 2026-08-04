"""由 packages/contracts/schemas/v1/retrieval-request.schema.json 生成，请勿手工编辑业务字段。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import KnowledgeBaseId, NonEmptyStr, PlatformUserId, SemVerStr, Timestamp, require_unique_items


class RetrievalFilters(BaseModel):
    """只允许已声明的文档 ID、语言和更新时间范围；不接受排序表达式。"""

    model_config = ConfigDict(extra="forbid")

    document_ids: list[KnowledgeBaseId] | None = Field(default=None, min_length=1, max_length=100)
    languages: list[NonEmptyStr] | None = Field(default=None, min_length=1, max_length=20)
    updated_since: Timestamp | None = None
    updated_until: Timestamp | None = None


class RetrievalRequest(BaseModel):
    """Research 向 Knowledge 请求受限多 KB Internal Retrieval；请求不得携带授权结论。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: SemVerStr = Field(description="与版本头一致的精确版本。")
    user_id: PlatformUserId = Field(description="Platform User ID；仅作为实时授权主体。")
    knowledge_base_ids: list[KnowledgeBaseId] = Field(
        min_length=1, max_length=50, description="所有目标 KB 均需当前 READ 权限。"
    )
    query: str = Field(min_length=1, max_length=8192, description="仅用于内部检索。")
    purpose: Literal["research_retrieval"]
    limit: int | None = Field(default=20, ge=1, le=100, description="最大命中数，缺省 20。")
    filters: RetrievalFilters | None = None

    @field_validator("knowledge_base_ids")
    @classmethod
    def _kb_ids_unique(cls, v):
        return require_unique_items(v, "knowledge_base_ids")
