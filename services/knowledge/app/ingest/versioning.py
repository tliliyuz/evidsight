"""版本化生命周期与原子发布 — 对齐 ADR-007 / RAG_PIPELINE.md §3/§4.2

职责：
- 对外 Document 状态映射（queued→queued，解析~验证→processing，ready→completed，
  ready_with_warnings→partial，failed→failed）
- 版本创建 / 递增 / Checkpoint / pending 查询
- 发布前完整性校验（Segment 数、Embedding 数、chunk_index 覆盖）
- 原子发布：KB 短时锁（index_status=updating + index_generation++）→ 写 staging
  向量 → 切换 active_version → 删旧版本向量 → 清理 staging → 恢复 ready
"""

import json
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.storage import local_storage
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.rag.bm25 import invalidate_bm25_cache_async

logger = logging.getLogger(__name__)

# ---- 版本状态常量（内部阶段名不对外泄漏）----
QUEUED = "queued"
PARSING = "parsing"
CHUNKING = "chunking"
EMBEDDING = "embedding"
INDEXING = "indexing"
VERIFYING = "verifying"
READY = "ready"
READY_WITH_WARNINGS = "ready_with_warnings"
FAILED = "failed"

# 解析至验证阶段 → 对外 processing
PROCESSING_STAGES: frozenset[str] = frozenset(
    {PARSING, CHUNKING, EMBEDDING, INDEXING, VERIFYING}
)
# 终态版本：不可再被 Worker 恢复
TERMINAL_VERSION_STATUSES: frozenset[str] = frozenset(
    {READY, READY_WITH_WARNINGS, FAILED}
)
# 可检索版本（Internal Retrieval 只读这些）
RETRIEVABLE_VERSION_STATUSES: frozenset[str] = frozenset(
    {READY, READY_WITH_WARNINGS}
)


class PublishAbortedError(Exception):
    """发布因删除流程中止（对齐 ADR-007：KB/Document 处于 deleting 时不发布）。

    由调用方（tasks）捕获并返回 failed 状态；不进入 publish 的 recovering 分支。
    """


def map_document_status(version_status: str) -> DocumentStatus:
    """版本状态 → 对外 Document 状态（ADR-007 固定映射，内部阶段名不得泄漏）。"""
    if version_status == QUEUED:
        return DocumentStatus.QUEUED
    if version_status in PROCESSING_STAGES:
        return DocumentStatus.PROCESSING
    if version_status == READY:
        return DocumentStatus.COMPLETED
    if version_status == READY_WITH_WARNINGS:
        return DocumentStatus.PARTIAL
    if version_status == FAILED:
        return DocumentStatus.FAILED
    raise ValueError(f"未知版本状态: {version_status}")


def build_version_chroma_id(doc_id: int, version_no: int, chunk_index: int) -> str:
    """版本作用域 Chroma id：doc_{doc_id}_v{version}_c{chunk_index}。"""
    return f"doc_{doc_id}_v{version_no}_c{chunk_index}"


async def count_active_version_chunks(db, kb_id: int) -> int:
    """统计 KB 当前 Active Version 覆盖的 chunks 总数（对齐 ADR-007：只计可检索版本）。

    复用 app/rag/bm25.py 加载前快速 COUNT 的 join 模式：Chunk join DocumentVersion
    join Document，仅当 Document.active_version == DocumentVersion.version 时计数，
    避免把旧版本 chunks 计入。
    """
    result = await db.execute(
        select(func.count())
        .select_from(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Chunk.kb_id == kb_id,
            Document.active_version == DocumentVersion.version,
        )
    )
    return result.scalar() or 0


async def count_version_chunks(db, version_id: int) -> int:
    """统计指定 Version 的 chunks 总数（发布成功后回填 doc.chunk_count）。"""
    result = await db.execute(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.document_version_id == version_id)
    )
    return result.scalar() or 0


async def next_version_number(db, doc_id: int) -> int:
    """同一 Document 内 version 递增且唯一：max(version)+1，无历史从 1 开始。"""
    result = await db.execute(
        select(func.max(DocumentVersion.version)).where(
            DocumentVersion.document_id == doc_id
        )
    )
    max_version = result.scalar()
    return (max_version or 0) + 1


async def create_document_version(db, doc: Document, *, source: str = "upload") -> DocumentVersion:
    """创建 queued 版本并把 Document 重置为 queued。

    source 用于审计（upload/reprocess），当前不落库，仅作为调用语义标记。
    """
    version_no = await next_version_number(db, doc.id)
    version = DocumentVersion(
        uuid=str(uuid_lib.uuid4()),
        document_id=doc.id,
        version=version_no,
        status=QUEUED,
    )
    db.add(version)
    doc.status = map_document_status(QUEUED)
    await db.flush()
    await db.commit()
    return version


async def update_version(db, version: DocumentVersion, **fields) -> None:
    """写入阶段 Checkpoint（status / last_success_batch / error_* / staging_* 等）并提交。"""
    for key, value in fields.items():
        setattr(version, key, value)
    await db.commit()


async def get_pending_version(db, doc: Document) -> DocumentVersion | None:
    """返回最新非终态版本；文档已全部终态则返回 None。"""
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None or version.status in TERMINAL_VERSION_STATUSES:
        return None
    return version


def verify_staging(
    declared_count: int,
    chunk_rows: list[dict],
    staging_rows: list[dict],
) -> list[str]:
    """发布前完整性校验（对齐 RAG_PIPELINE.md §4.2 验证清单）。

    返回问题列表；空列表表示通过。
    """
    issues: list[str] = []
    if len(chunk_rows) != declared_count:
        issues.append(
            f"Segment 数不一致: 解析声明={declared_count}, MySQL={len(chunk_rows)}"
        )
    if len(staging_rows) != len(chunk_rows):
        issues.append(
            f"Embedding 数量不一致: staging={len(staging_rows)}, MySQL={len(chunk_rows)}"
        )
    staging_indices = {r["chunk_index"] for r in staging_rows}
    chunk_indices = {c["chunk_index"] for c in chunk_rows}
    if staging_indices != chunk_indices:
        issues.append("Staging 与 MySQL 的 chunk_index 集合不一致")
    return issues


async def publish_version(db, kb, doc, version, store, staging_rows) -> None:
    """原子发布。

    Args:
        db: MySQL 会话（MySQL 为唯一权威）
        kb: KnowledgeBase ORM
        doc: Document ORM
        version: DocumentVersion ORM（发布前可预置为 ready_with_warnings 以表达部分可用）
        store: ChromaVectorStore（在线 per-KB Collection）
        staging_rows: list[dict]，每项含 segment_uuid / chunk_index / content /
            embedding / metadata

    Raises:
        PublishAbortedError: KB 或 Document 处于删除流程，发布中止（version 置 failed）。
    """
    # 0. 删除流程守卫（对齐 ADR-007）：deleting 状态不发布，避免发布后被删除器误删
    if kb.status != "active" or doc.status == DocumentStatus.DELETING:
        version.status = FAILED
        version.error_msg = "知识库或文档处于删除流程，发布中止"
        await db.commit()
        raise PublishAbortedError("发布中止：知识库或文档处于删除流程")

    # 1. KB 短时发布锁：置 updating 并递增 index_generation
    kb.index_status = "updating"
    kb.index_generation = (kb.index_generation or 0) + 1
    await db.commit()

    try:
        # 2. 将 staging 向量写入现有 per-KB Collection（版本作用域 Chroma id）
        ids = [
            build_version_chroma_id(doc.id, version.version, r["chunk_index"])
            for r in staging_rows
        ]
        await store.add(
            ids=ids,
            kb_id=kb.id,
            documents=[r["content"] for r in staging_rows],
            embeddings=[r["embedding"] for r in staging_rows],
            metadatas=[
                {
                    **r.get("metadata", {}),
                    "kb_id": kb.id,
                    "doc_id": doc.id,
                    "version": version.version,
                    "chunk_index": r["chunk_index"],
                }
                for r in staging_rows
            ],
        )

        # 3. MySQL 事务切换 active_version + 版本终态
        final_status = (
            version.status if version.status in (READY, READY_WITH_WARNINGS) else READY
        )
        doc.active_version = version.version
        version.status = final_status
        version.published_at = datetime.now(timezone.utc)
        doc.status = map_document_status(final_status)
        await db.commit()

        # 4. 删除旧 Version 向量（doc_id 级定位，version != 当前）
        # Chroma where 只允许顶层单个逻辑操作符，组合条件须用 $and 包裹
        # （实测 ChromaDB 0.5.23 对扁平双键 where 抛 "exactly one operator"）
        await store.delete(
            kb_id=kb.id,
            where={
                "$and": [
                    {"doc_id": doc.id},
                    {"version": {"$ne": version.version}},
                ]
            },
        )

        # 5. 在线集合一致性校验（对齐 ADR-007「校验在线集合」）：新版本向量
        #    应全部落在在线 Collection；缺失即发布失败 → recovering，
        #    由恢复器依据 Active Version 补齐或回滚（不静默接受丢失）
        expected = {
            build_version_chroma_id(doc.id, version.version, r["chunk_index"])
            for r in staging_rows
        }
        actual = set(await store.get_ids(
            kb_id=kb.id,
            where={"$and": [{"doc_id": doc.id}, {"version": version.version}]},
        ))
        if actual != expected:
            missing = sorted(expected - actual)
            logger.error(
                "发布后在线集合校验失败: kb_id=%d doc_id=%d version=%d missing=%s",
                kb.id, doc.id, version.version, missing,
            )
            raise RuntimeError(
                f"在线集合校验失败，缺失 {len(missing)} 个向量（示例: {missing[:5]}）"
            )

        # 6. 清理 staging 产物
        if version.staging_artifact_key:
            await local_storage.delete(version.staging_artifact_key)

        # 7. 恢复 KB 就绪
        kb.index_status = "ready"
        await db.commit()
    except Exception:
        # 发布失败：解除锁（recovering），恢复器依据 Active Version 补齐或回滚
        kb.index_status = "recovering"
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        raise

    # 7. BM25 缓存失效（发布后索引集已变化，TTL 只作兜底）
    await invalidate_bm25_cache_async(kb.id)


async def read_staging_artifact(artifact_key: str) -> list[dict]:
    """读取 staging JSON 产物（崩溃恢复路径）。"""
    raw = await local_storage.read(artifact_key)
    rows = json.loads(raw.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("staging 产物格式非法：预期 JSON 数组")
    return rows


async def write_staging_artifact(kb_id: int, version_uuid: str, staging_rows: list[dict]) -> str:
    """写入 staging JSON 产物并返回 artifact key（uploads/staging/{kb_id}/{version_uuid}.json）。"""
    from pathlib import Path

    from app.config import settings

    artifact_key = str(
        Path(settings.UPLOAD_DIR) / "staging" / str(kb_id) / f"{version_uuid}.json"
    )
    await local_storage.save_bytes(
        artifact_key,
        json.dumps(staging_rows, ensure_ascii=False).encode("utf-8"),
    )
    return artifact_key
