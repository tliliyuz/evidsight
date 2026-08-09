"""会话 v1 API — 创建/列表/详情/重命名/删除（对齐 API.md §7）。

薄适配器复用既有 service（create_conversation/list_conversations/
get_conversation_detail/rename_conversation/delete_conversation）。v1 创建
请求统一使用 knowledge_base_id（对齐 Chat v1 与 API.md §3.1），映射到
service 的 ConversationCreate.kb_uuid。更新用 PATCH，删除返回 204 无正文。
"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid_helpers import resolve_uuid_to_id
from app.dependencies import get_current_user, get_db
from app.models.conversation import Conversation
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationV1Create,
)
from app.services.conversation_service import (
    create_conversation,
    delete_conversation,
    get_conversation_detail,
    list_conversations,
    rename_conversation,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["会话 v1"])


@router.post("", status_code=201)
async def create_conversation_v1(
    req: ConversationV1Create,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建会话并绑定单个知识库（knowledge_base_id）。"""
    legacy = ConversationCreate(kb_uuid=req.knowledge_base_id, title=req.title)
    data = await create_conversation(db, current_user["user_id"], legacy)
    return {"code": "0", "message": "会话创建成功", "data": data.model_dump()}


@router.get("")
async def list_conversations_v1(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """当前用户会话列表（按 last_message_at 倒序，分页）。"""
    data = await list_conversations(db, current_user["user_id"], page, page_size)
    return {"code": "0", "message": "ok", "data": data.model_dump()}


@router.get("/{conversation_id}")
async def get_conversation_v1(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """会话详情（含消息历史），仅 owner 可访问。"""
    conv_internal_id = await resolve_uuid_to_id(db, Conversation, conversation_id)
    data = await get_conversation_detail(db, conv_internal_id, current_user["user_id"])
    return {"code": "0", "message": "ok", "data": data.model_dump()}


@router.patch("/{conversation_id}")
async def rename_conversation_v1(
    conversation_id: str,
    req: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重命名会话；仅 owner 可操作。"""
    conv_internal_id = await resolve_uuid_to_id(db, Conversation, conversation_id)
    data = await rename_conversation(db, conv_internal_id, current_user["user_id"], req)
    return {"code": "0", "message": "ok", "data": data.model_dump()}


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation_v1(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除会话及其全部消息（硬删除）；返回 204 无正文。"""
    conv_internal_id = await resolve_uuid_to_id(db, Conversation, conversation_id)
    await delete_conversation(db, conv_internal_id, current_user["user_id"])
    return Response(status_code=204)
