"""知识库业务逻辑 — 创建/查询/更新/删除"""

import logging
import time
import uuid as uuid_lib

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.core.exceptions import (
    KnowledgeBaseNameExistsException,
    KnowledgeBaseNotFoundException,
)
from app.core.permissions import require_kb_readable, require_kb_writable
from app.core.utils import escape_like
from app.core.uuid_helpers import resolve_user_display
from app.ingest.delete_tasks import delete_kb as delete_kb_task
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseDeleteResponse,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    PublicKnowledgeBaseListResponse,
    PublicKnowledgeBaseResponse,
)

logger = logging.getLogger(__name__)


def _pool_status() -> str:
    """获取数据库连接池状态（用于诊断连接池耗尽）"""
    try:
        pool = engine.sync_engine.pool
        return (
            f"pool[size={pool.size()}, checkedin={pool.checkedin()}, "
            f"checkedout={pool.checkedout()}, overflow={pool.overflow()}]"
        )
    except Exception:
        return "pool[unavailable]"


async def _get_real_chunk_counts(db: AsyncSession, kb_ids: list[int]) -> dict[int, int]:
    """查询指定 KB 的实时分块总数（从 Chunk 表 COUNT，非 KB 表缓存列）。

    只统计各 Document 当前 Active Version 的 chunks（对齐 ADR-007 / P1 重算语义），
    避免旧版本 chunks 计入。用于替代 KnowledgeBase.chunk_count 静态缓存列，
    避免 Celery 任务更新延迟或失败导致的僵尸计数值。
    """
    if not kb_ids:
        return {}
    t0 = time.time()
    result = await db.execute(
        select(Chunk.kb_id, func.count(Chunk.id))
        .select_from(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Chunk.kb_id.in_(kb_ids),
            Document.active_version == DocumentVersion.version,
        )
        .group_by(Chunk.kb_id)
    )
    counts = {row.kb_id: row[1] for row in result.all()}
    t = time.time() - t0
    if t > 0.1:
        logger.warning(
            "_get_real_chunk_counts kb_ids=%s SLOW=%.3fs %s",
            kb_ids,
            t,
            _pool_status(),
        )
    return counts


async def _get_real_doc_counts(db: AsyncSession, kb_ids: list[int]) -> dict[int, int]:
    """查询指定 KB 的实时文档总数（从 Document 表 COUNT，非 KB 表缓存列）。

    用于替代 KnowledgeBase.doc_count 静态缓存列，避免批量上传中
    doc_count 更新延迟或会话脏数据导致的僵尸计数值。
    """
    if not kb_ids:
        return {}
    t0 = time.time()
    result = await db.execute(
        select(Document.kb_id, func.count(Document.id))
        .where(
            Document.kb_id.in_(kb_ids),
            Document.status != DocumentStatus.DELETING,
        )
        .group_by(Document.kb_id)
    )
    counts = {row.kb_id: row[1] for row in result.all()}
    t = time.time() - t0
    if t > 0.1:
        logger.warning(
            "_get_real_doc_counts kb_ids=%s SLOW=%.3fs %s",
            kb_ids,
            t,
            _pool_status(),
        )
    return counts


async def create_kb(
    db: AsyncSession, user_id: int, data: KnowledgeBaseCreate
) -> KnowledgeBaseResponse:
    """创建知识库，同名冲突时抛出 KnowledgeBaseNameExistsException"""
    kb = KnowledgeBase(
        uuid=str(uuid_lib.uuid4()),
        user_id=user_id,
        name=data.name,
        description=data.description,
        visibility=data.visibility,
    )
    db.add(kb)
    try:
        await db.flush()
    except IntegrityError:
        raise KnowledgeBaseNameExistsException(data.name)
    await db.refresh(kb)
    # B 类：响应 owner 字段输出 Platform User UUID，不暴露内部 users.id
    owner_uuid, owner_username = await resolve_user_display(db, user_id)
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


async def get_kb(
    db: AsyncSession,
    kb_id: int,
    user_id: int | None = None,
    role: str | None = None,
    *,
    fill_chunk_count: bool = True,
) -> KnowledgeBase:
    """获取知识库，不存在时抛出 KnowledgeBaseNotFoundException。

    权限规则（visibility 优先于 ownership）：
    - public KB：所有登录用户可读
    - private KB：仅 owner 或 admin 可读

    fill_chunk_count=True（默认）时从 Chunk/Document 表实时查询
    分块数与文档数，替代 KB 表 chunk_count/doc_count 缓存列，
    消除 Celery 任务延迟或批量上传会话脏数据导致的僵尸计数。
    内部调用（如 check_kb_active）无需此值时传 False 避免额外查询。
    """
    t_start = time.time()

    t0 = time.time()
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    t_select = time.time() - t0

    if kb is None:
        raise KnowledgeBaseNotFoundException(kb_id)
    if user_id is not None:
        require_kb_readable(kb, user_id, role or "")

    t_chunk = 0.0
    if fill_chunk_count:
        real_chunk_counts = await _get_real_chunk_counts(db, [kb_id])
        real_doc_counts = await _get_real_doc_counts(db, [kb_id])
        kb.chunk_count = real_chunk_counts.get(kb_id, kb.chunk_count)
        kb.doc_count = real_doc_counts.get(kb_id, kb.doc_count)
        t_chunk = time.time() - t_start - t_select  # 近似（含查询 overhead）

    t_total = time.time() - t_start
    if t_total > 0.3:
        logger.warning(
            "get_kb kb_id=%d SLOW SELECT=%.3fs CHUNK=%.3fs TOTAL=%.3fs %s",
            kb_id,
            t_select,
            t_chunk,
            t_total,
            _pool_status(),
        )

    return kb


async def list_kbs(
    db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
) -> KnowledgeBaseListResponse:
    """获取用户的知识库列表（分页）"""
    # 总数
    count_q = (
        select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.user_id == user_id)
    )
    total = (await db.execute(count_q)).scalar()

    # 分页数据
    q = (
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == user_id)
        .order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    # 实时查询分块数与文档数（替代 KB 表缓存列，消除僵尸计数）
    kb_ids = [r.id for r in rows]
    real_chunk_counts = await _get_real_chunk_counts(db, kb_ids)
    real_doc_counts = await _get_real_doc_counts(db, kb_ids)

    # B 类：owner 输出 Platform User UUID + 用户名（列表内所有 KB 属于同一 user，解析一次）
    owner_uuid, owner_username = await resolve_user_display(db, user_id)

    items = []
    for r in rows:
        resp = KnowledgeBaseResponse(
            uuid=r.uuid,
            name=r.name,
            description=r.description,
            owner=owner_uuid,
            visibility=r.visibility,
            status=r.status,
            doc_count=r.doc_count,
            chunk_count=r.chunk_count,
            created_at=r.created_at,
            updated_at=r.updated_at,
            index_status=r.index_status,
            owner_username=owner_username,
        )
        resp.chunk_count = real_chunk_counts.get(r.id, 0)
        resp.doc_count = real_doc_counts.get(r.id, 0)
        items.append(resp)

    return KnowledgeBaseListResponse(total=total, page=page, page_size=page_size, items=items)


async def list_public_kbs(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> PublicKnowledgeBaseListResponse:
    """获取所有公开知识库列表（分页），仅返回 status=active 且 visibility=public 的 KB"""
    base_q = (
        select(KnowledgeBase, User.username, User.platform_user_id)
        .join(User, KnowledgeBase.user_id == User.id)
        .where(
            KnowledgeBase.visibility == "public",
            KnowledgeBase.status == "active",
        )
    )
    # 总数
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar()

    # 分页数据
    q = (
        base_q.order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).all()

    # 实时查询分块数与文档数（替代 KB 表缓存列，消除僵尸计数）
    kb_ids = [kb.id for kb, _, _ in rows]
    real_chunk_counts = await _get_real_chunk_counts(db, kb_ids)
    real_doc_counts = await _get_real_doc_counts(db, kb_ids)

    # B 类：owner 输出 Platform User UUID（JOIN 已带出），不暴露内部 users.id
    items = [
        PublicKnowledgeBaseResponse(
            uuid=kb.uuid,
            name=kb.name,
            description=kb.description,
            owner=platform_user_id,
            username=username,
            visibility=kb.visibility,
            status=kb.status,
            doc_count=real_doc_counts.get(kb.id, 0),
            chunk_count=real_chunk_counts.get(kb.id, 0),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb, username, platform_user_id in rows
    ]

    return PublicKnowledgeBaseListResponse(total=total, page=page, page_size=page_size, items=items)


async def list_visible_kbs(
    db: AsyncSession,
    user_id: int,
    role: str,
    *,
    scope: str = "all",
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> KnowledgeBaseListResponse:
    """获取当前用户可见的知识库统一列表（API.md §6.1 / FRONTEND §5.3）。

    scope 语义：
    - mine：当前用户全部 KB（含 deleting）
    - public：visibility=public 且 status=active（跨用户，含自己的公开 KB）
    - all（默认）：普通用户为 mine ∪ public（SQL OR 按主键天然去重）；
      admin 返回全部 KB（治理可见，对齐 PRD §8.2）
    q 对 name 做 LIKE %q% 模糊搜索（转义 %/_）；排序 updated_at DESC NULLS LAST；
    服务端分页，计数与响应复用实时 chunk/doc 计数避免僵尸缓存列。
    """
    conditions: list = []
    if scope == "mine":
        conditions.append(KnowledgeBase.user_id == user_id)
    elif scope == "public":
        conditions.append(KnowledgeBase.visibility == "public")
        conditions.append(KnowledgeBase.status == "active")
    elif scope == "all":
        if role != "admin":
            conditions.append(
                or_(
                    KnowledgeBase.user_id == user_id,
                    and_(
                        KnowledgeBase.visibility == "public",
                        KnowledgeBase.status == "active",
                    ),
                )
            )
    if q:
        conditions.append(KnowledgeBase.name.like(f"%{escape_like(q)}%", escape="\\"))

    count_q = select(func.count()).select_from(KnowledgeBase).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q_sel = (
        select(KnowledgeBase)
        .where(*conditions)
        # MySQL 8.0 不支持 `NULLS LAST` 字面量语法；用 `IS NULL` 先行排序实现
        # 「updated_at DESC NULLS LAST」（NULL 排最后）。
        .order_by(KnowledgeBase.updated_at.is_(None), KnowledgeBase.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q_sel)).scalars().all()

    kb_ids = [r.id for r in rows]
    real_chunk_counts = await _get_real_chunk_counts(db, kb_ids)
    real_doc_counts = await _get_real_doc_counts(db, kb_ids)

    # B 类：owner 输出 Platform User UUID + 用户名。列表可能跨用户（public/all），
    # 按去重后的 user_id 逐个解析一次。
    owner_display_map: dict[int, tuple[str, str]] = {}
    for uid in {r.user_id for r in rows}:
        owner_display_map[uid] = await resolve_user_display(db, uid)

    items = []
    for r in rows:
        owner_uuid, owner_username = owner_display_map[r.user_id]
        resp = KnowledgeBaseResponse(
            uuid=r.uuid,
            name=r.name,
            description=r.description,
            owner=owner_uuid,
            visibility=r.visibility,
            status=r.status,
            doc_count=r.doc_count,
            chunk_count=r.chunk_count,
            created_at=r.created_at,
            updated_at=r.updated_at,
            index_status=r.index_status,
            owner_username=owner_username,
        )
        resp.chunk_count = real_chunk_counts.get(r.id, 0)
        resp.doc_count = real_doc_counts.get(r.id, 0)
        items.append(resp)

    return KnowledgeBaseListResponse(total=total, page=page, page_size=page_size, items=items)


async def update_kb(
    db: AsyncSession, kb_id: int, user_id: int, role: str, data: KnowledgeBaseUpdate
) -> KnowledgeBaseResponse:
    """更新知识库元数据（名称/描述/可见性）。
    owner 可修改自己的 KB；admin 可修改任意 KB（含 visibility 修正）。
    """
    kb = await get_kb(db, kb_id)

    require_kb_writable(kb, user_id, role)

    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    if data.visibility is not None:
        kb.visibility = data.visibility

    try:
        await db.flush()
    except IntegrityError:
        raise KnowledgeBaseNameExistsException(data.name or kb.name)

    await db.refresh(kb)
    # B 类：owner 输出 Platform User UUID + 用户名（admin 修改他人 KB 时以 kb.user_id 为准）
    owner_uuid, owner_username = await resolve_user_display(db, kb.user_id)
    resp = KnowledgeBaseResponse(
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
    # db.refresh() 会用 DB 缓存列的僵尸值覆盖 get_kb() 已填充的实时计数，需重新修正
    real_chunk_counts = await _get_real_chunk_counts(db, [kb_id])
    real_doc_counts = await _get_real_doc_counts(db, [kb_id])
    resp.chunk_count = real_chunk_counts.get(kb_id, resp.chunk_count)
    resp.doc_count = real_doc_counts.get(kb_id, resp.doc_count)
    return resp


async def delete_kb(
    db: AsyncSession, kb_id: int, user_id: int, role: str
) -> KnowledgeBaseDeleteResponse:
    """删除知识库（仅标记 status=deleting，不做物理删除）"""
    kb = await get_kb(db, kb_id)

    require_kb_writable(kb, user_id, role)

    kb.status = "deleting"
    await db.flush()
    await db.refresh(kb)
    await db.commit()

    # 分发 Celery 异步删除任务（commit 后再分发，避免 Worker 在事务提交前读到旧状态）
    delete_kb_task.delay(kb.id)

    return KnowledgeBaseDeleteResponse(kb_uuid=kb.uuid, status=kb.status)


async def check_kb_active(db: AsyncSession, kb_id: int) -> KnowledgeBase:
    """检查知识库存在且 status==active，否则抛异常。
    供文档上传/检索/reprocess 等服务调用。
    """
    kb = await get_kb(db, kb_id, fill_chunk_count=False)
    if kb.status != "active":
        raise KnowledgeBaseNotFoundException(kb_id)
    return kb
