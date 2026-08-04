"""由 packages/contracts/schemas/v1/evidence-resolve-request.schema.json 生成，请勿手工编辑业务字段。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import (
    InternalSourceIdentity,
    PlatformUserId,
    SemVerStr,
    require_unique_items,
)


class EvidenceResolveRequest(BaseModel):
    """按稳定身份重新取得已经选定的内部候选正文；不得用文本查询猜测原命中。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: SemVerStr
    user_id: PlatformUserId = Field(description="当前授权主体。")
    references: list[InternalSourceIdentity] = Field(min_length=1, max_length=100)
    purpose: Literal["research_evidence_resolve"]

    @field_validator("references")
    @classmethod
    def _references_unique(cls, v):
        return require_unique_items(v, "references")
