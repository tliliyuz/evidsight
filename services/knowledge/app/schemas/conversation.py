"""会话请求/响应模型 — 对齐 API.md §5"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ── 请求模型 ──


class ConversationCreate(BaseModel):
    """POST /api/conversations 请求体"""

    kb_uuid: str = Field(..., description="关联知识库 UUID")
    title: str | None = Field(None, max_length=256, description="会话标题，不传则默认'新对话'")


class ConversationUpdate(BaseModel):
    """PUT /api/conversations/{uuid} 请求体"""

    title: str = Field(..., min_length=1, max_length=256, description="新标题")


class ConversationV1Create(BaseModel):
    """POST /api/v1/conversations 请求体（v1 契约使用 knowledge_base_id，对齐 Chat v1）

    legacy 的 ConversationCreate.kb_uuid 不沿用到 v1 契约；由 v1 路由映射到
    service 的 kb_uuid（API.md §7 / docs/openapi/evidsight-v1.yaml）。
    """

    knowledge_base_id: str = Field(..., description="关联知识库 UUID")
    title: str | None = Field(None, max_length=256, description="会话标题，不传则默认'新对话'")


# ── 响应模型 ──


class MessageResponse(BaseModel):
    """消息响应（Message 不改造，保持 integer id）"""

    id: int
    role: str
    content: str
    thinking_content: str | None = None
    created_at: datetime
    sources: list[dict] = Field(
        default_factory=list,
        description="来源引用 canonical wire 投影（SSE sources 持久化，API.md §12），无来源为 []",
    )

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _hydrate_sources(cls, value: Any) -> Any:
        """ORM Message 从 metadata 列水合 sources；dict 输入保持原样（缺省 []）。"""
        if isinstance(value, dict):
            return value
        meta = getattr(value, "metadata_", None) or {}
        if isinstance(meta, dict):
            sources = meta.get("sources") or []
        else:
            sources = []
        attrs = getattr(value, "__dict__", None)
        if isinstance(attrs, dict):
            attrs["sources"] = sources
        return value


class ConversationResponse(BaseModel):
    """会话响应（列表项 + 详情共用）"""

    uuid: str
    owner_user_id: str = Field(description="owner 用户 Platform User UUID（非内部 users.id）")
    kb_uuid: str | None = Field(
        None,
        description="关联知识库 UUID（kb 删除后为 null）",
    )
    kb_status: str | None = Field(
        None,
        description="关联知识库状态：active=正常 / deleted=已删除 / unavailable=不可访问。"
        "kb_id 为 null 且 original_kb_uuid 非 null 时为 deleted",
    )
    kb_name: str | None = Field(
        None,
        description="关联知识库名称（含已删除/不可访问的），前端用于孤儿会话提示。"
        "孤儿会话从 original_kb_name 读取",
    )
    original_kb_uuid: str | None = Field(
        None,
        description="KB 删除前的原始 UUID，用于孤儿会话审计追踪",
    )
    original_kb_name: str | None = Field(
        None,
        description="KB 删除前的原始名称，用于孤儿会话 Banner 展示",
    )
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = Field(
        None,
        description="最后一次产生消息的时间，列表排序字段。新创建尚无消息的会话为 null",
    )

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    """会话详情响应（含消息列表）"""

    messages: list[MessageResponse] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    """会话列表分页响应"""

    total: int
    page: int
    page_size: int
    items: list[ConversationResponse]
