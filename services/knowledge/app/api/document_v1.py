"""文档 v1 API — 上传/列表/详情/分块/重试/删除（对齐 API.md §6.2）。

两个路由器：
- kb_doc_router（prefix /api/v1/knowledge-bases）：嵌套文档集合（上传 202 / 列表 200）
- doc_v1_router（prefix /api/v1/documents）：文档级操作，路径不再依赖 legacy
  嵌套 {kb_id}/documents/{doc_uuid}；文档 uuid 反解出 kb_id 后复用既有 service。

删除返回 204 无正文，重试路径名为 retry 返回 202；location 端点已在
app/api/document.py 的 v1_router 注册，不重复。上传/重试/删除语义对齐
API.md §6.2 目标态（legacy 的 201/reprocess/202 不替代）。
"""

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid_helpers import get_by_uuid, resolve_uuid_to_id
from app.dependencies import get_current_user, get_db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.document_service import (
    delete_document,
    get_document,
    get_document_chunks,
    list_documents,
    reprocess_document,
    upload_document,
)

kb_doc_router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["文档 v1"])
doc_v1_router = APIRouter(prefix="/api/v1/documents", tags=["文档 v1"])


@kb_doc_router.post("/{kb_id}/documents", status_code=202)
async def upload_document_v1(
    kb_id: str,
    file: UploadFile = File(...),
    force: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上传单个文档（multipart/form-data），202 接受，提交事务后分发入库。"""
    kb_internal_id = await resolve_uuid_to_id(db, KnowledgeBase, kb_id)
    data = await upload_document(
        db, kb_internal_id, current_user["user_id"], current_user["role"], file, force
    )
    return {"code": "0", "message": "文档上传成功，已加入处理队列", "data": data.model_dump()}


@kb_doc_router.get("/{kb_id}/documents")
async def list_documents_v1(
    kb_id: str,
    status: str | None = Query(None, description="按状态过滤"),
    filename: str | None = Query(None, description="按文件名模糊搜索"),
    sort_by: str = Query("created_at", description="排序字段"),
    order: str = Query("desc", description="排序方向 asc/desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取知识库下的文档列表（筛选 + 排序 + 分页）。public KB 允许任意登录用户只读。"""
    kb_internal_id = await resolve_uuid_to_id(db, KnowledgeBase, kb_id)
    data = await list_documents(
        db,
        kb_internal_id,
        current_user["user_id"],
        current_user["role"],
        status=status,
        filename=filename,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    return {"code": "0", "message": "ok", "data": data.model_dump()}


async def _resolve_doc_kb_id(db: AsyncSession, document_id: str) -> tuple[Document, int]:
    """按 document uuid 解析文档行并取出其 kb_id。

    v1 文档级路径不再携带 kb_id；复用 get_by_uuid（不存在抛 E2001 404），
    返回 (doc, kb_id) 供 service 完成 KB READ 鉴权。
    """
    doc = await get_by_uuid(db, Document, document_id)
    return doc, doc.kb_id


@doc_v1_router.get("/{document_id}")
async def get_document_v1(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """文档详情（KB READ 权限约束）。"""
    doc, kb_id = await _resolve_doc_kb_id(db, document_id)
    data = await get_document(db, kb_id, doc.id, current_user["user_id"], current_user["role"])
    return {"code": "0", "message": "ok", "data": data.model_dump()}


@doc_v1_router.get("/{document_id}/chunks")
async def get_document_chunks_v1(
    document_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """文档分块列表（分页，含稳定 segment_id 契约，生产环境截断 content 至预览）。"""
    doc, kb_id = await _resolve_doc_kb_id(db, document_id)
    data = await get_document_chunks(
        db,
        kb_id,
        doc.id,
        current_user["user_id"],
        current_user["role"],
        page=page,
        page_size=page_size,
    )
    return {"code": "0", "message": "ok", "data": data.model_dump()}


@doc_v1_router.post("/{document_id}/retry", status_code=202)
async def reprocess_document_v1(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重新处理文档（仅终态 completed/partial/failed 允许，幂等）；202 接受。"""
    doc, kb_id = await _resolve_doc_kb_id(db, document_id)
    data = await reprocess_document(
        db, kb_id, doc.id, current_user["user_id"], current_user["role"]
    )
    return {"code": "0", "message": "重新处理任务已提交", "data": data.model_dump()}


@doc_v1_router.delete("/{document_id}", status_code=204)
async def delete_document_v1(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除文档（标记 deleting，异步清理向量+文件+记录）；返回 204 无正文。"""
    doc, kb_id = await _resolve_doc_kb_id(db, document_id)
    await delete_document(db, kb_id, doc.id, current_user["user_id"], current_user["role"])
    return Response(status_code=204)
