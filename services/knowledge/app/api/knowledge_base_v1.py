"""知识库 v1 API — 创建/统一可见列表/详情/更新/删除（对齐 API.md §6.1）。

本模块是薄适配器：复用既有 service（create_kb/get_kb/update_kb/delete_kb/
list_visible_kbs）与 uuid 解析，仅调整路径与 HTTP 语义。删除返回 204
无正文；更新用 PATCH 部分更新；统一可见列表以 scope/q 查询参数服务
FRONTEND §5.3 的「全部 / 我创建的 / 组织公开」筛选与名称搜索。
"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid_helpers import resolve_user_display, resolve_uuid_to_id
from app.dependencies import get_current_user, get_db
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base_service import (
    create_kb,
    delete_kb,
    get_kb,
    list_visible_kbs,
    update_kb,
)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["知识库 v1"])


@router.post("", status_code=201)
async def create_knowledge_base_v1(
    req: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建知识库"""
    kb = await create_kb(db, current_user["user_id"], req)
    return kb


@router.get("")
async def list_knowledge_bases_v1(
    scope: str = Query("all", pattern="^(all|mine|public)$", description="可见范围筛选"),
    q: str | None = Query(None, max_length=128, description="按名称模糊搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """统一可见列表：全部 / 我创建的 / 组织公开 + 名称搜索（API.md §6.1）"""
    data = await list_visible_kbs(
        db,
        current_user["user_id"],
        current_user["role"],
        scope=scope,
        q=q,
        page=page,
        page_size=page_size,
    )
    return data


@router.get("/{kb_id}")
async def get_knowledge_base_v1(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """知识库详情。public 所有登录用户可读，private 仅 owner 或 admin 可读。"""
    kb_internal_id = await resolve_uuid_to_id(db, KnowledgeBase, kb_id)
    kb = await get_kb(db, kb_internal_id, current_user["user_id"], current_user["role"])
    # B 类：owner 输出 Platform User UUID + 用户名，不暴露内部 users.id
    owner_uuid, owner_username = await resolve_user_display(db, kb.user_id)
    return KnowledgeBaseResponse(
        uuid=kb.uuid,
        name=kb.name,
        description=kb.description,
        owner=owner_uuid,
        visibility=kb.visibility,
        status=kb.status,
        doc_count=kb.doc_count,
        chunk_count=kb.chunk_count,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        index_status=kb.index_status,
        owner_username=owner_username,
    )


@router.patch("/{kb_id}")
async def update_knowledge_base_v1(
    kb_id: str,
    req: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新知识库元数据（部分更新：name/description/visibility 均可选）。
    owner 可修改自己的 KB，admin 可修正任意 KB。"""
    kb_internal_id = await resolve_uuid_to_id(db, KnowledgeBase, kb_id)
    kb = await update_kb(db, kb_internal_id, current_user["user_id"], current_user["role"], req)
    return kb


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base_v1(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除知识库（标记 status=deleting，异步清理）；返回 204 无正文。"""
    kb_internal_id = await resolve_uuid_to_id(db, KnowledgeBase, kb_id)
    await delete_kb(db, kb_internal_id, current_user["user_id"], current_user["role"])
    return Response(status_code=204)
