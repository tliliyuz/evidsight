"""Internal Retrieval / Evidence Resolve 服务层 — 权限感知检索与稳定身份解析。

对齐 API.md §11.2、contracts/README.md §3（处理顺序）、RAG_PIPELINE.md §7。
处理顺序固定：Research 服务身份 → Contract 版本与结构 → 用户 active → 逐 KB READ
权限 → 检索 / 解析。任一步失败不执行后续；目标 KB 中任一无权整次失败。

本模块不向调用方暴露 ORM/路径/缓存/嵌入等内部细节；命中对象只含契约允许字段
（见 retrieval-hit.schema.json / evidence-resolve-response.schema.json）。
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import async_session
from app.core.exceptions import PermissionDeniedException, RetrievalServiceException
from app.core.permissions import require_kb_readable
from app.core.redis_client import get_async_redis
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.rag.bm25 import BM25Retriever
from app.rag.fusion import rrf_fusion
from app.rag.retriever import RetrievalOutput, VectorRetriever

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1.0.0"

# 只有这些版本状态参与检索 / 解析；其余（queued/failed 等）视为不可用来源
_RETRIEVABLE_VERSION_STATUSES = frozenset({"ready", "ready_with_warnings"})

_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


class InternalRetrievalError(Exception):
    """契约错误信封信号；由 API 层转换为 error-response.schema.json。"""

    def __init__(self, status_code: int, error_code: str, message: str,
                 retryable: bool = False):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def _fmt_utc(dt: datetime | None) -> str | None:
    """datetime → RFC3339 UTC（Z 结尾，固定宽度）。naive 视为 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _load_active_user(db: AsyncSession, platform_user_id: str) -> User | None:
    """按 Platform UUID 加载用户；仅 active 用户可继续，否则返回 None。"""
    result = await db.execute(
        select(User).where(User.platform_user_id == platform_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        return None
    return user


async def _load_kb(db: AsyncSession, kb_uuid: str) -> KnowledgeBase | None:
    """按 KB UUID 加载知识库；不存在返回 None。"""
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.uuid == kb_uuid)
    )
    return result.scalar_one_or_none()


def _require_kb_readable(kb: KnowledgeBase, user: User) -> None:
    """READ 权限检查，失败抛 KB_FORBIDDEN 信号。"""
    try:
        require_kb_readable(kb, user.id, user.role)
    except PermissionDeniedException:
        raise InternalRetrievalError(403, "KB_FORBIDDEN",
                                     "目标知识库不可访问", False) from None


def _require_kb_active(kb: KnowledgeBase) -> None:
    """KB 状态失败关闭：deleting 状态立即拒绝新检索/解析（DATABASE.md §5.1）。

    与不可读统一映射为 KB_FORBIDDEN，避免向 Consumer 泄露删除中的资源状态。
    """
    if kb.status != "active":
        raise InternalRetrievalError(403, "KB_FORBIDDEN",
                                     "目标知识库不可访问", False)


async def _require_kb_ready(db: AsyncSession, kb: KnowledgeBase) -> None:
    """索引就绪检查；未就绪时抛 503 可重试信号。

    对齐 RAG_PIPELINE.md §4.2 / ADR-007：index_status == 'updating' 表示发布锁
    持有中（原子切换窗口），做有界等待（PUBLISH_LOCK_WAIT_MS，默认 5s）轮询
    刷新 KB 状态；等待期间切换完成即放行。超时仍 updating，或处于
    recovering/其他不可恢复状态，直接抛 503 可重试。
    """
    if kb.index_status != "ready":
        if kb.index_status == "updating":
            deadline = time.monotonic() + settings.PUBLISH_LOCK_WAIT_MS / 1000
            while time.monotonic() < deadline:
                await asyncio.sleep(0.2)
                await db.refresh(kb)
                if kb.index_status == "ready":
                    return
        raise InternalRetrievalError(
            503, "INTERNAL_RETRIEVAL_UNAVAILABLE",
            "知识库索引尚未就绪", True,
        )


async def _retrieve_kb(
    db: AsyncSession, kb_id: int, query: str, top_k: int = 20,
    document_ids: list[str] | None = None,
) -> RetrievalOutput:
    """对单个 KB 执行向量 + BM25 双路检索并 RRF 融合。

    该函数是 Provider 成功路径的 monkeypatch 目标（测试屏蔽
    ChromaDB/Embedding/BM25），签名不得随意变更。

    Args:
        db: 数据库会话
        kb_id: 知识库内部 id（向量检索按 kb_id 路由 collection）
        query: 查询文本
        top_k: 每路召回上限
        document_ids: 仅检索这些文档（Document UUID）；为 None 时不限

    Raises:
        RetrievalServiceException: 检索链路不可用
    """
    outputs: list[RetrievalOutput] = []

    try:
        outputs.append(await VectorRetriever().search(query, kb_id, top_k=top_k))
    except RetrievalServiceException:
        logger.exception("向量检索失败: kb_id=%d", kb_id)
        raise

    try:
        bm25 = BM25Retriever(
            async_redis=await get_async_redis(),
            session_factory=async_session,
        )
        # BM25 缓存 key 含 index_generation：publish 递增 generation 后自动失效
        kb_row = await db.get(KnowledgeBase, kb_id)
        generation = kb_row.index_generation if kb_row is not None else 0
        outputs.append(await bm25.search(
            query, kb_id, top_k=top_k, index_generation=generation,
        ))
    except RetrievalServiceException:
        logger.exception("BM25 检索失败: kb_id=%d", kb_id)
        raise

    output = rrf_fusion(*outputs)
    if document_ids:
        output = await _filter_by_document_ids(db, output, document_ids)
    return output


async def _filter_by_document_ids(
    db: AsyncSession, output: RetrievalOutput, document_ids: list[str],
) -> RetrievalOutput:
    """按 Document UUID 集合过滤召回结果（对齐 retrieval-request.filters.document_ids）。"""
    result = await db.execute(
        select(Document.id).where(Document.uuid.in_(document_ids))
    )
    allowed = set(result.scalars().all())
    output.results = [r for r in output.results if r.doc_id in allowed]
    output.total = len(output.results)
    return output


async def _map_hit(
    db: AsyncSession, kb: KnowledgeBase, result, rank: int,
) -> dict | None:
    """RetrievalResult → 契约 RetrievalHit；无法解析稳定身份或来源信息时返回 None。

    只返回 Active Version 下、带稳定 segment_uuid 的命中；缺失任一稳定身份
    （Document / Active Version / Segment）时丢弃该命中，不伪造 Evidence。
    """
    doc_result = await db.execute(select(Document).where(Document.id == result.doc_id))
    doc = doc_result.scalar_one_or_none()
    if doc is None or doc.active_version is None:
        return None

    ver_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version == doc.active_version,
        )
    )
    ver = ver_result.scalar_one_or_none()
    if ver is None or ver.status not in _RETRIEVABLE_VERSION_STATUSES:
        return None

    chunk_result = await db.execute(
        select(Chunk).where(
            Chunk.doc_id == result.doc_id,
            Chunk.chunk_index == result.chunk_index,
        )
    )
    chunk = chunk_result.scalar_one_or_none()
    if chunk is None or not chunk.segment_uuid or chunk.document_version_id != ver.id:
        return None

    content = (result.content or "").strip()
    if not content:
        return None

    # 位置：优先检索结果页码，其次 chunk 元数据，再次章节路径；无位置则丢弃
    page = result.page
    if page is None and chunk.metadata_:
        page = chunk.metadata_.get("page")
    if page is not None:
        location = {"page_number": int(page)}
    else:
        section_path: list[str] = []
        if result.section_path:
            section_path = [p.strip() for p in result.section_path.split(">") if p.strip()]
        if section_path:
            location = {"section_path": section_path}
        else:
            return None

    section_title = result.section_title
    if not section_title and chunk.metadata_:
        section_title = chunk.metadata_.get("section_title")

    source_updated_at = (
        _fmt_utc(doc.updated_at)
        or _fmt_utc(ver.published_at)
        or _fmt_utc(datetime.now(timezone.utc))
    )

    hit: dict = {
        "hit_id": str(uuid4()),
        "knowledge_base_id": kb.uuid,
        "document_id": doc.uuid,
        "document_version_id": ver.uuid,
        "segment_id": chunk.segment_uuid,
        "document_display_name": (doc.display_name or doc.filename or "未知文档").strip(),
        "location": location,
        "minimal_excerpt": content,
        "scores": [{"score_kind": "rrf", "value": result.score, "rank": rank}],
        "source_updated_at": source_updated_at,
        "retrieved_at": _fmt_utc(datetime.now(timezone.utc)),
        "access_scope": "internal",
    }
    if section_title:
        hit["section_title"] = section_title
    return hit


async def search_internal(db: AsyncSession, body: dict, request_id: str) -> dict:
    """执行权限感知检索并返回 retrieval-response 契约响应体。"""
    user = await _load_active_user(db, body["user_id"])
    if user is None:
        raise InternalRetrievalError(403, "AUTH_USER_DISABLED",
                                     "用户不存在或已被禁用", False)

    # 逐 KB READ 校验：任一无权或不存在整次失败（对齐 contracts/README.md §3）
    kbs: list[KnowledgeBase] = []
    for kb_uuid in body["knowledge_base_ids"]:
        kb = await _load_kb(db, kb_uuid)
        if kb is None:
            raise InternalRetrievalError(403, "KB_FORBIDDEN",
                                         "目标知识库不可访问", False)
        _require_kb_active(kb)
        _require_kb_readable(kb, user)
        kbs.append(kb)

    # 任一 KB 索引未就绪 → 有界等待（updating）或直接 503 可重试
    for kb in kbs:
        await _require_kb_ready(db, kb)

    query = body["query"]
    limit = body.get("limit", 20)
    filters = body.get("filters") or {}
    document_ids = filters.get("document_ids")

    all_hits: list[dict] = []
    for kb in kbs:
        try:
            output = await _retrieve_kb(
                db, kb.id, query, top_k=limit, document_ids=document_ids,
            )
        except Exception:
            logger.exception("KB %d 检索失败", kb.id)
            raise InternalRetrievalError(
                503, "INTERNAL_RETRIEVAL_UNAVAILABLE",
                "检索服务暂时不可用", True,
            ) from None
        for result in output.results:
            hit = await _map_hit(db, kb, result, rank=0)
            if hit is not None:
                all_hits.append(hit)

    # 按 segment_id 去重（同一次请求内同一 Segment 只保留首个命中）
    seen: set[str] = set()
    deduped: list[dict] = []
    for hit in all_hits:
        key = hit["segment_id"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)

    results = deduped[:limit]
    for i, hit in enumerate(results, start=1):
        hit["scores"][0]["rank"] = i

    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "results": results,
        "returned_count": len(results),
        "has_more": len(all_hits) > len(results),
    }


async def resolve_internal(db: AsyncSession, body: dict, request_id: str) -> dict:
    """解析 Evidence 引用并返回 evidence-resolve-response 契约响应体。

    先对全部引用目标 KB 做 READ 校验（任一失败整次失败），再逐引用解析
    稳定身份；任一引用不可用整批失败，不返回部分结果。
    """
    user = await _load_active_user(db, body["user_id"])
    if user is None:
        raise InternalRetrievalError(403, "AUTH_USER_DISABLED",
                                     "用户不存在或已被禁用", False)

    kb_cache: dict[str, KnowledgeBase] = {}
    for ref in body["references"]:
        kb_uuid = ref["knowledge_base_id"]
        if kb_uuid in kb_cache:
            continue
        kb = await _load_kb(db, kb_uuid)
        if kb is None:
            raise InternalRetrievalError(403, "KB_FORBIDDEN",
                                         "目标知识库不可访问", False)
        _require_kb_active(kb)
        _require_kb_readable(kb, user)
        kb_cache[kb_uuid] = kb

    results = []
    for ref in body["references"]:
        kb = kb_cache[ref["knowledge_base_id"]]
        results.append(await _resolve_one(db, kb, ref))

    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "results": results,
    }


async def _resolve_one(db: AsyncSession, kb: KnowledgeBase, ref: dict) -> dict:
    """解析单个引用：文档 → Active Version → Segment 稳定身份与最小正文。

    任一环节缺失 / 不匹配当前 Active 状态 → EVIDENCE_SOURCE_UNAVAILABLE（整批失败）。
    """
    doc_result = await db.execute(
        select(Document).where(Document.uuid == ref["document_id"])
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None or doc.kb_id != kb.id:
        raise InternalRetrievalError(400, "EVIDENCE_SOURCE_UNAVAILABLE",
                                     "引用文档当前不可用", False)

    ver_result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.uuid == ref["document_version_id"])
    )
    ver = ver_result.scalar_one_or_none()
    if (ver is None or ver.document_id != doc.id
            or ver.version != doc.active_version
            or ver.status not in _RETRIEVABLE_VERSION_STATUSES):
        raise InternalRetrievalError(400, "EVIDENCE_SOURCE_UNAVAILABLE",
                                     "引用版本当前不可用", False)

    chunk_result = await db.execute(
        select(Chunk).where(Chunk.segment_uuid == ref["segment_id"])
    )
    chunk = chunk_result.scalar_one_or_none()
    if (chunk is None or chunk.doc_id != doc.id
            or chunk.document_version_id != ver.id
            or not chunk.content or not chunk.content.strip()):
        raise InternalRetrievalError(400, "EVIDENCE_SOURCE_UNAVAILABLE",
                                     "引用来源当前不可用", False)

    page = None
    if chunk.metadata_:
        page = chunk.metadata_.get("page")
    if page is not None:
        location = {"page_number": int(page)}
    else:
        location = {"section_path": ["来源"]}

    source_updated_at = (
        _fmt_utc(doc.updated_at)
        or _fmt_utc(ver.published_at)
        or _fmt_utc(datetime.now(timezone.utc))
    )

    return {
        "knowledge_base_id": kb.uuid,
        "document_id": doc.uuid,
        "document_version_id": ver.uuid,
        "segment_id": chunk.segment_uuid,
        "minimal_excerpt": chunk.content.strip(),
        "location": location,
        "source_updated_at": source_updated_at,
    }
