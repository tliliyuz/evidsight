"""Celery 异步入库流水线任务 — 版本化写路径（对齐 ADR-007 / RAG_PIPELINE.md §3/§4.2）

每次首次入库或重处理创建独立 DocumentVersion：
  queued → parsing → chunking → embedding → verifying → ready（任一不可恢复错误 → failed）

- Worker 以 Version UUID 为幂等键；重复投递不生成重复 Chunk/向量
- MySQL 的 Document/Version/Chunk 状态是生命周期唯一权威
- Embedding 先写受控 staging 产物，发布时校验后原子切换 active_version
- 旧 Active Version 在发布前继续服务
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, update

from app.config import settings
from app.core.chroma_client import get_vector_store
from app.core.database import async_session
from app.ingest.celery_app import celery_app
from app.ingest.lock import (
    acquire_version_lock_async,
    release_version_lock_async,
)
from app.ingest.versioning import (
    CHUNKING,
    EMBEDDING,
    INDEXING,
    PARSING,
    QUEUED,
    READY_WITH_WARNINGS,
    VERIFYING,
    PublishAbortedError,
    count_active_version_chunks,
    count_version_chunks,
    map_document_status,
    publish_version,
    read_staging_artifact,
    verify_staging,
    write_staging_artifact,
)
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.section import Section
from app.rag.chunker import chunk_document
from app.rag.cleaner import clean_parse_result
from app.rag.embedder import embed_chunks
from app.rag.parser import parse_document

logger = logging.getLogger(__name__)

# Worker 进程持久化事件循环，避免「每任务新建 loop → 关闭」导致 SQLAlchemy 连接池
# 中的连接挂在旧 loop 上，下个任务在新 loop 中复用时触发「attached to a different loop」
_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


@celery_app.task(
    bind=True, max_retries=3, soft_time_limit=600, autoretry_for=(Exception,), retry_backoff=True
)
def ingest_version(self, version_id: int) -> dict:
    """版本化入库主流水线（Celery 同步入口 → 异步执行）。

    返回格式: {"status": str, "version_id": int}
    未捕获异常自动重试（max_retries=3），利用 Version 状态与 Checkpoint 断点续传。
    """
    return _get_worker_loop().run_until_complete(_ingest_version_async(version_id))


@celery_app.task(
    bind=True, max_retries=3, soft_time_limit=600, autoretry_for=(Exception,), retry_backoff=True
)
def ingest_document(self, doc_id: int) -> dict:
    """兼容桥接：查找文档最新 pending version → 投递 ingest_version。

    保持旧调用方（document_service.upload/reprocess）不变期间的兼容入口；
    新调用方直接投递 ingest_version(version_id)。
    """
    return _get_worker_loop().run_until_complete(_ingest_document_async(doc_id))


class _LoadDocStatus:
    """_load_doc 返回状态常量"""

    OK = "ok"
    NOT_FOUND = "not_found"
    DELETING = "deleting"


@dataclass
class _LoadDocResult:
    """_load_doc 返回值：区分文档不存在、已标记删除、正常加载三种情况"""

    doc: Document | None
    status: str  # _LoadDocStatus


async def _load_doc(db, doc_id: int) -> _LoadDocResult:
    """加载文档记录并检查 DELETING 状态。

    Returns:
        _LoadDocResult: status 为 OK/NOT_FOUND/DELETING，
                        status=OK 时 doc 一定非 None，
                        status≠OK 时 doc 一定为 None。
    """
    doc = await db.get(Document, doc_id)
    if doc is None:
        return _LoadDocResult(doc=None, status=_LoadDocStatus.NOT_FOUND)
    if doc.status == DocumentStatus.DELETING:
        logger.info("文档 %d 已被标记删除，中止流水线", doc_id)
        return _LoadDocResult(doc=None, status=_LoadDocStatus.DELETING)
    return _LoadDocResult(doc=doc, status=_LoadDocStatus.OK)


async def _ingest_document_async(doc_id: int) -> dict:
    """兼容桥接实现：查找 pending version → 委派给版本化流水线。"""
    async with async_session() as db:
        doc = await db.get(Document, doc_id)
        if doc is None:
            return {"status": "not_found", "doc_id": doc_id}
        if doc.status == DocumentStatus.DELETING:
            return {"status": "deleting", "doc_id": doc_id}
        version = await _latest_pending_version(db, doc.id)
        if version is None:
            return {"status": "no_pending_version", "doc_id": doc_id}
        version_id = version.id
    return await _ingest_version_async(version_id)


async def _latest_pending_version(db, doc_id: int) -> DocumentVersion | None:
    """返回文档最新非终态版本。"""
    from app.ingest.versioning import TERMINAL_VERSION_STATUSES

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None or version.status in TERMINAL_VERSION_STATUSES:
        return None
    return version


async def _ingest_version_async(version_id: int) -> dict:
    """版本化流水线异步入口：加载 Version/Document → 获取 Version 幂等锁 → 阶段派发。"""
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        if version is None:
            return {"status": "not_found", "version_id": version_id}
        version_uuid = version.uuid
        doc = await db.get(Document, version.document_id)
        if doc is None:
            return {"status": "not_found", "version_id": version_id}
        if doc.status == DocumentStatus.DELETING:
            logger.info("Version %s 所属文档已删除，中止", version_uuid)
            return {"status": "deleting", "version_id": version_id}

    # 幂等锁：Version UUID（对齐 ADR-007，重复投递不生成重复 Chunk/向量）
    if not await acquire_version_lock_async(version_uuid):
        logger.warning("Version %s 幂等锁已被占用，拒绝重复投递", version_uuid)
        return {"status": "locked", "version_id": version_id}

    try:
        return await _ingest_version_locked(version_id)
    finally:
        await release_version_lock_async(version_uuid)


async def _ingest_version_locked(version_id: int) -> dict:
    """持锁后的阶段派发：按 version.status 分叉执行。"""
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        if version is None:
            return {"status": "not_found", "version_id": version_id}
        doc = await db.get(Document, version.document_id)
        if doc is None:
            return {"status": "not_found", "version_id": version_id}
        stage = version.status

        if not doc.file_path:
            await _mark_version_failed(db, version, doc, "FILE_MISSING", "文件路径为空，无法解析")
            return {"status": "failed", "version_id": version_id}

    if stage in (QUEUED, PARSING, CHUNKING):
        # queued：完整流水线；parsing/chunking：未写 chunks，降级重新 parse
        return await _run_parse_embed_publish(version_id)
    if stage == EMBEDDING:
        return await _run_embed_resume(version_id)
    if stage in (INDEXING, VERIFYING):
        # staging 已写入 → 校验 → 发布
        return await _run_publish_from_staging(version_id)

    # 终态（ready/ready_with_warnings/failed）→ 不处理
    return {"status": stage, "version_id": version_id}


async def _run_parse_embed_publish(version_id: int) -> dict:
    """完整流水线：parse → clean → chunk → 写 MySQL（含 version_id+segment_uuid）→ embed → staging → 校验 → 发布。"""
    # 1. 标记 parsing
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        file_path = doc.file_path
        file_type = doc.file_type
        version.status = PARSING
        doc.status = map_document_status(PARSING)
        await db.commit()

    # 2. 解析 + 清洗（CPU 操作，DB session 外执行）
    parse_result = parse_document(file_path, file_type)
    if settings.CLEAN_ENABLED:
        parse_result = clean_parse_result(
            parse_result,
            strip_boilerplate=settings.CLEAN_STRIP_BOILERPLATE,
            normalize_space=settings.CLEAN_NORMALIZE_WHITESPACE,
            repair_unicode=settings.CLEAN_REPAIR_UNICODE,
        )

    # 3. 空文档 / 失败率判定
    if parse_result.total_pages == 0 or not parse_result.full_text.strip():
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db, version, doc, "EMPTY_DOC", "文档无有效内容，解析后全文为空"
            )
        return {"status": "failed", "version_id": version_id}

    if parse_result.failure_rate > settings.PARSE_FAILURE_FAILED:
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db,
                version,
                doc,
                "PARSE_FAILED",
                _build_error_msg(parse_result, settings.PARSE_FAILURE_FAILED),
            )
        return {"status": "failed", "version_id": version_id}

    # 4. 分块（CPU 操作）
    chunking_result = chunk_document(parse_result.full_text, parse_result.pages)
    if chunking_result.total_chunks == 0:
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db, version, doc, "EMPTY_CHUNKS", "文档分块结果为空，无有效文本内容"
            )
        return {"status": "failed", "version_id": version_id}

    # 5. 写入 chunks（携带 document_version_id + segment_uuid + 版本作用域 chroma_id）
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        await _replace_sections_and_chunks(db, doc.id, doc.kb_id, chunking_result, version)
        version.expected_segment_count = chunking_result.total_chunks
        version.last_success_batch = 0
        version.status = EMBEDDING
        doc.status = map_document_status(EMBEDDING)
        await db.commit()

    # 6. 从 MySQL 重载 chunk rows（真实 DB id，供 token 回写）
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        chunk_rows = await _load_version_chunk_rows(db, version.document_id, version.id)
        if not chunk_rows:
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db, version, doc, "CHUNKS_MISSING", "分块数据丢失，无法继续 Embedding"
            )
            return {"status": "failed", "version_id": version_id}
        warning_summary = parse_result.warnings[:5] if parse_result.failed_pages > 0 else None

    # 7. Embedding → staging → 校验 → 发布
    return await _embed_and_publish(
        version_id,
        chunk_rows,
        resume_batch=0,
        declared_count=chunking_result.total_chunks,
        warning_summary=warning_summary,
    )


async def _run_embed_resume(version_id: int) -> dict:
    """断点恢复：chunks 已写入 → 从 last_success_batch 续传 Embedding → staging → 发布。"""
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        chunk_rows = await _load_version_chunk_rows(db, doc.id, version.id)
        if not chunk_rows:
            await _mark_version_failed(
                db, version, doc, "CHUNKS_MISSING", "分块数据丢失，无法继续 Embedding"
            )
            return {"status": "failed", "version_id": version_id}
        resume_batch = version.last_success_batch or 0
        declared_count = version.expected_segment_count or len(chunk_rows)
        warning_summary = version.warning_summary

    return await _embed_and_publish(
        version_id, chunk_rows, resume_batch, declared_count, warning_summary
    )


async def _run_publish_from_staging(version_id: int) -> dict:
    """崩溃恢复：staging 已写入 → 从 artifact 读取 → 校验 → 发布。"""
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        if not version.staging_artifact_key:
            await _mark_version_failed(
                db, version, doc, "STAGING_MISSING", "staging 产物缺失，无法发布"
            )
            return {"status": "failed", "version_id": version_id}
        artifact_key = version.staging_artifact_key

    try:
        staging_rows = await read_staging_artifact(artifact_key)
    except Exception as e:
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db, version, doc, "STAGING_READ_FAILED", f"staging 产物读取失败: {e}"
            )
        return {"status": "failed", "version_id": version_id}

    # 与 MySQL chunk rows 比对校验
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        chunk_rows = await _load_version_chunk_rows(db, doc.id, version.id)
        declared_count = version.expected_segment_count or len(chunk_rows)

    issues = verify_staging(declared_count, chunk_rows, staging_rows)
    if issues:
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(db, version, doc, "VERIFY_FAILED", "; ".join(issues))
        return {"status": "failed", "version_id": version_id}

    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        kb = await db.get(KnowledgeBase, doc.kb_id)
        try:
            await publish_version(db, kb, doc, version, get_vector_store(), staging_rows)
        except PublishAbortedError:
            # 删除流程中止：version 已由 publish 置 failed，此处仅返回失败状态
            logger.warning("Version %d 发布因删除流程中止", version_id)
            return {"status": "failed", "version_id": version_id}
        # 崩溃恢复路径此前不更新计数：发布成功后重算（对齐 P1 重算语义）
        doc.chunk_count = await count_version_chunks(db, version.id)
        kb.chunk_count = await count_active_version_chunks(db, kb.id)
        await db.commit()

    return {"status": map_document_status(version.status).value, "version_id": version_id}


async def _embed_and_publish(
    version_id: int,
    chunk_rows: list[dict[str, Any]],
    resume_batch: int,
    declared_count: int,
    warning_summary: list[str] | None = None,
) -> dict:
    """Embedding → 增量 staging 写入 → 发布前校验 → 原子发布。

    staging 产物逐批写入（每批后 checkpoint + artifact），崩溃后可从 artifact
    恢复已嵌入 Segment，再续传剩余批次；artifact 缺失时从 0 重做。
    """
    # 1. 标记 embedding
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        version.status = EMBEDDING
        doc.status = map_document_status(EMBEDDING)
        await db.commit()
        kb_id = doc.kb_id

    # 2. 加载已有部分 staging 产物（断点恢复）
    staging_rows: list[dict[str, Any]] = []
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        if version.staging_artifact_key:
            try:
                staging_rows = await read_staging_artifact(version.staging_artifact_key)
            except Exception:
                logger.warning("Version %d staging 产物残缺，作废重做", version_id)
                staging_rows = []
                version.staging_artifact_key = None
                await db.commit()
        elif resume_batch > 0:
            # checkpoint 存在但产物缺失：嵌入数据丢失，从 0 重做
            logger.warning(
                "Version %d checkpoint=%d 但无 staging 产物，从 0 重做", version_id, resume_batch
            )
            resume_batch = 0

    # 3. 分批 Embedding + 逐批增量写 staging
    token_map: dict[int, int] = {}
    try:
        batch_size = settings.EMBED_BATCH_SIZE
        total_batches = (len(chunk_rows) + batch_size - 1) // batch_size
        for batch_no in range(resume_batch, total_batches):
            batch_start = batch_no * batch_size
            batch_end = min(batch_start + batch_size, len(chunk_rows))
            batch_texts = [chunk_rows[i]["content"] for i in range(batch_start, batch_end)]
            embed_result = await embed_chunks(batch_texts)

            for i in range(len(batch_texts)):
                row_idx = batch_start + i
                row = chunk_rows[row_idx]
                meta = row.get("metadata") or {}
                staging_rows.append(
                    {
                        "segment_uuid": row["segment_uuid"],
                        "chunk_index": row["chunk_index"],
                        "content": row["content"],
                        "embedding": embed_result.embeddings[i],
                        "metadata": {
                            "page": meta.get("page"),
                            "section_title": row.get("section_title", ""),
                            "section_path": row.get("section_path", ""),
                            "section_id": row.get("section_id"),
                        },
                    }
                )
                token_map[row["id"]] = embed_result.token_counts[i]

            # 批次级 checkpoint + 增量写 staging 产物
            async with async_session() as db:
                version = await db.get(DocumentVersion, version_id)
                if version is None:
                    continue
                version.last_success_batch = batch_no + 1
                version.embedded_segment_count = len(staging_rows)
                version.staging_artifact_key = await write_staging_artifact(
                    kb_id, version.uuid, staging_rows
                )
                await db.commit()
    except Exception as e:
        logger.exception("Version %d Embedding 向量化失败", version_id)
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(
                db, version, doc, "EMBED_FAILED", f"Embedding 向量化失败: {e}"
            )
        return {"status": "failed", "version_id": version_id, "error": str(e)}

    # 4. 发布前校验（对齐 RAG_PIPELINE.md §4.2）
    issues = verify_staging(declared_count, chunk_rows, staging_rows)
    if issues:
        async with async_session() as db:
            version = await db.get(DocumentVersion, version_id)
            doc = await db.get(Document, version.document_id)
            await _mark_version_failed(db, version, doc, "VERIFY_FAILED", "; ".join(issues))
        return {"status": "failed", "version_id": version_id, "error": "; ".join(issues)}

    # 5. 原子发布
    async with async_session() as db:
        version = await db.get(DocumentVersion, version_id)
        doc = await db.get(Document, version.document_id)
        kb = await db.get(KnowledgeBase, doc.kb_id)
        if version.warning_summary:
            version.status = READY_WITH_WARNINGS
        try:
            await publish_version(db, kb, doc, version, get_vector_store(), staging_rows)
        except PublishAbortedError:
            # 删除流程中止：version 已由 publish 置 failed，此处仅返回失败状态
            logger.warning("Version %d 发布因删除流程中止", version_id)
            return {"status": "failed", "version_id": version_id}
        # 回写 token_count（DashScope API 实际值覆盖 chunker 估算值）
        for chunk_id, actual_tokens in token_map.items():
            if chunk_id is not None:
                await db.execute(
                    update(Chunk).where(Chunk.id == chunk_id).values(token_count=actual_tokens)
                )
        # 计数重算（对齐 P1）：kb.chunk_count 不累加，按 Active Version 重算，
        # 避免旧版本混入或重复发布导致膨胀；doc.chunk_count 即当前版本 chunk_rows
        doc.chunk_count = len(chunk_rows)
        kb.chunk_count = await count_active_version_chunks(db, kb.id)
        await db.commit()

    return {
        "status": map_document_status(version.status).value,
        "version_id": version_id,
        "chunks": len(chunk_rows),
    }


async def _load_version_chunk_rows(db, doc_id: int, version_id: int) -> list[dict[str, Any]]:
    """加载指定 Version 的全部 chunks（按 chunk_index 排序），返回提取后的数据列表。

    只读取该 Version 的 chunks，避免新旧版本混杂。
    """
    result = await db.execute(
        select(Chunk)
        .where(Chunk.doc_id == doc_id, Chunk.document_version_id == version_id)
        .order_by(Chunk.chunk_index)
    )
    chunks_db = result.scalars().all()
    rows: list[dict[str, Any]] = []
    for c in chunks_db:
        meta = c.metadata_ or {}
        rows.append(
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "chroma_id": c.chroma_id,
                "section_id": c.section_id,
                "segment_uuid": c.segment_uuid,
                "section_title": meta.get("section_title", ""),
                "section_path": meta.get("section_path", ""),
                "page": meta.get("page"),
                "metadata": meta,
            }
        )
    return rows


async def _replace_sections_and_chunks(
    db, doc_id: int, kb_id: int, chunking_result, version: DocumentVersion
) -> None:
    """写入当前 Version 的 section/chunk 结构（幂等：先清理同 Version 旧数据）。

    Chunk 携带 document_version_id 与稳定 Segment UUID；Chroma id 版本作用域。
    """
    await db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
    await db.execute(delete(Section).where(Section.document_version_id == version.id))

    section_ids: list[int] = []
    for section_result in chunking_result.sections:
        section = Section(
            doc_id=doc_id,
            document_version_id=version.id,
            kb_id=kb_id,
            title=section_result.title,
            path=section_result.path,
            level=section_result.level,
            start_chunk_index=section_result.start_chunk_index,
            end_chunk_index=section_result.end_chunk_index,
        )
        db.add(section)
        await db.flush()
        if section.id is None:
            raise RuntimeError("Section 写入后未生成主键")
        section_ids.append(section.id)

    for chunk_result in chunking_result.chunks:
        meta: dict[str, object] = {}
        if chunk_result.page_number is not None:
            meta["page"] = chunk_result.page_number
        if chunk_result.section_title is not None:
            meta["section_title"] = chunk_result.section_title
        if chunk_result.section_path is not None:
            meta["section_path"] = chunk_result.section_path

        section_id = (
            section_ids[chunk_result.section_index]
            if chunk_result.section_index is not None
            else None
        )
        import uuid as uuid_lib

        chunk = Chunk(
            doc_id=doc_id,
            document_version_id=version.id,
            kb_id=kb_id,
            section_id=section_id,
            segment_uuid=str(uuid_lib.uuid4()),
            chroma_id=f"doc_{doc_id}_v{version.version}_c{chunk_result.chunk_index}",
            content=chunk_result.content,
            chunk_index=chunk_result.chunk_index,
            token_count=chunk_result.estimated_tokens,
            metadata_=meta if meta else None,
        )
        db.add(chunk)


async def _mark_version_failed(
    db, version: DocumentVersion, doc: Document, error_code: str, error_summary: str
) -> None:
    """不可恢复错误 → version failed + doc failed（error_code/error_summary 安全摘要）。"""
    version.status = "failed"
    version.error_code = error_code
    version.error_summary = error_summary[:500]
    doc.status = DocumentStatus.FAILED
    doc.error_msg = error_summary
    await db.commit()


def _build_error_msg(parse_result, threshold: float) -> str:
    """构建容错错误信息"""
    # docx 按段落解析用"段"，其余按页
    unit = "段" if parse_result.source_type == "docx" else "页"
    base = (
        f"解析失败率 {parse_result.failure_rate:.0%}，"
        f"超过 {threshold:.0%} 阈值。"
        f"（{parse_result.failed_pages}/{parse_result.total_pages} {unit}失败）"
    )
    if parse_result.warnings:
        base += " " + "; ".join(parse_result.warnings[:5])  # 最多记录 5 条
        if len(parse_result.warnings) > 5:
            base += f" ... 等共 {len(parse_result.warnings)} 条警告"
    return base
