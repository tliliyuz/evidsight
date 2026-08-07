"""由 packages/contracts/schemas/v1/error-response.schema.json 生成，请勿手工编辑业务字段。"""

from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import NonEmptyStr, RequestId

ErrorCode = Literal[
    "INTERNAL_SERVICE_UNAUTHENTICATED",
    "INTERNAL_CONTRACT_UNSUPPORTED",
    "INTERNAL_CONTRACT_INVALID",
    "AUTH_USER_DISABLED",
    "INTERNAL_IDENTITY_UNAVAILABLE",
    "KB_FORBIDDEN",
    "INTERNAL_RATE_LIMITED",
    "INTERNAL_RETRIEVAL_UNAVAILABLE",
    "EVIDENCE_SOURCE_UNAVAILABLE",
]


class ErrorDetail(BaseModel):
    """受控错误细节；禁止包含正文、查询原文、凭证、堆栈、内部路径或缓存 Key。"""

    model_config = ConfigDict(extra="forbid")

    error_code: ErrorCode = Field(description="稳定错误码。")
    message: NonEmptyStr = Field(description="面向调用方的最小安全摘要。")
    request_id: RequestId = Field(description="跨服务请求关联 ID。")
    retryable: bool = Field(description="调用方是否可安全重试。")
    details: Dict[str, object] = Field(
        default_factory=dict,
        description="可选受控细节；禁止 query/token/stack/path/excerpt 键。",
    )


class ErrorResponse(BaseModel):
    """Internal Contract 统一错误信封。"""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
