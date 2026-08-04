"""由 packages/contracts/schemas/v1/retrieval-response.schema.json 生成，请勿手工编辑业务字段。"""
from pydantic import BaseModel, ConfigDict, Field

from .common import NonNegativeInt, RequestId, SemVerStr
from .retrieval_hit import RetrievalHit


class RetrievalResponse(BaseModel):
    """Knowledge 对 Internal Retrieval 的响应；returned_count 必须等于 results 长度。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: SemVerStr
    request_id: RequestId = Field(description="回显跨服务请求关联 ID。")
    results: list[RetrievalHit]
    returned_count: NonNegativeInt = Field(ge=0, description="必须等于 results 长度。")
    has_more: bool
