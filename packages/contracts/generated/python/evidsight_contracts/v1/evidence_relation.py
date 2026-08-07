"""由 packages/contracts/schemas/v1/evidence-relation.schema.json 生成，请勿手工编辑业务字段。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import ClaimId, EvidenceId, NonEmptyStr, RelationId, UnitInterval


class EvidenceRelation(BaseModel):
    """证据与结论之间的独立关系对象；同一 Evidence 可关联多个结论。"""

    model_config = ConfigDict(extra="forbid")

    relation_id: RelationId
    evidence_id: EvidenceId
    claim_id: ClaimId
    relation_type: Literal["supports", "contradicts", "context"]
    confidence: UnitInterval = Field(ge=0, le=1, description="0—1 置信度。")
    rationale: NonEmptyStr | None = Field(default=None, description="安全摘要，不得复制内部原文。")
