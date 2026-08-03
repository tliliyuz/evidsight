"""由 packages/contracts/schemas/v1/identity-status-response.schema.json 生成，请勿手工编辑业务字段。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import NonNegativeInt, PlatformUserId, SemVerStr


class IdentityStatusResponse(BaseModel):
    """Knowledge 返回的最小权威用户状态。只有 active 用户产生成功响应。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: SemVerStr = Field(
        description="Provider 实际使用的精确 Contract 版本。"
    )
    platform_user_id: PlatformUserId = Field(
        description="被查询的 Platform User ID。"
    )
    status: Literal["active"] = Field(
        description="只有 active 用户产生成功响应；禁用或不存在用户产生 AUTH_USER_DISABLED 错误响应。"
    )
    status_version: NonNegativeInt = Field(
        ge=0,
        description="Knowledge 权威状态版本；未来状态缓存必须按此版本失效或更新。",
    )
