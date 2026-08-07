"""版本化入库流水线验收测试 — app.ingest.tasks._ingest_version_async

对齐 ADR-007 与 RAG_PIPELINE.md §3/§4.2：
- Worker 以 Version UUID 为幂等键，重复投递不生成重复 Chunk/向量
- 阶段机 queued → parsing → chunking → embedding → verifying → ready
- Chunk 写入携带 document_version_id + segment_uuid；Chroma id 版本作用域
- Embedding 先写 staging 产物，发布时校验后原子切换
- 不可恢复错误 → failed（error_code / error_summary）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase


def _make_version(status="queued", version_no=1, version_id=99):
    v = MagicMock(spec=DocumentVersion)
    v.id = version_id
    v.uuid = f"ver-uuid-{version_no}"
    v.document_id = 1
    v.version = version_no
    v.status = status
    v.last_success_batch = None
    v.expected_segment_count = None
    v.embedded_segment_count = None
    v.indexed_segment_count = None
    v.staging_artifact_key = None
    v.warning_summary = None
    v.error_code = None
    v.error_summary = None
    v.published_at = None
    return v


def _make_doc():
    d = MagicMock(spec=Document)
    d.id = 1
    d.uuid = "doc-uuid"
    d.kb_id = 1
    d.filename = "test.pdf"
    d.file_type = "pdf"
    d.file_path = "/tmp/test.pdf"
    d.status = None
    d.active_version = None
    d.chunk_count = 0
    d.error_msg = None
    return d


def _make_kb():
    kb = MagicMock(spec=KnowledgeBase)
    kb.id = 1
    kb.index_status = "ready"
    kb.index_generation = 0
    kb.status = "active"
    kb.chunk_count = 0
    kb.doc_count = 0
    return kb


def _make_stateful_store():
    """Chroma store mock：add 记录 ids，get_ids 按 doc_id+version 回放。

    模拟在线 Collection 的一致性（ADR-007「校验在线集合」）：add 写入后
    get_ids 能读到同一批版本作用域 id。
    """
    store = AsyncMock()
    added: list[tuple[int, int, str]] = []

    async def _add(ids, kb_id, **kwargs):
        metas = kwargs.get("metadatas") or []
        for chroma_id, meta in zip(ids, metas):
            added.append((meta["doc_id"], meta["version"], chroma_id))

    async def _get_ids(kb_id, where=None):
        doc_id = version = None
        for cond in (where or {}).get("$and", []):
            if "doc_id" in cond:
                doc_id = cond["doc_id"]
            elif "version" in cond and isinstance(cond["version"], int):
                version = cond["version"]
        return [
            cid
            for (d, v, cid) in added
            if (doc_id is None or d == doc_id) and (version is None or v == version)
        ]

    store.add = AsyncMock(side_effect=_add)
    store.get_ids = AsyncMock(side_effect=_get_ids)
    return store


def _make_chunk_rows(count=2, doc_id=1, version_no=1, version_id=99):
    """构造 MySQL 中已写入的 Chunk mock 行（embedding 恢复路径用）。"""
    rows = []
    for i in range(count):
        c = MagicMock()
        c.id = 100 + i
        c.chunk_index = i
        c.content = f"chunk {i}"
        c.chroma_id = f"doc_{doc_id}_v{version_no}_c{i}"
        c.section_id = 50 + i
        c.metadata_ = {
            "section_title": f"章节 {i}",
            "section_path": f"章节 {i}",
            "page": 1,
        }
        c.segment_uuid = f"00000000-0000-0000-0000-{i:012d}"
        c.document_version_id = version_id
        rows.append(c)
    return rows


def _make_db(doc, version, kb, chunks=None):
    """状态化 AsyncSession mock：execute 返回新增的 Chunk 对象（幂等去重后查询可见）。"""
    db = AsyncMock()
    added: list = []

    def _add(obj):
        # 模拟 DB flush 分配主键（对齐现有 test_tasks fixture 模式）
        if obj.__class__.__name__ == "Section":
            obj.id = 100
        added.append(obj)

    db.add = MagicMock(side_effect=_add)

    def _get(model, pk):
        if model is DocumentVersion:
            return version
        if model is Document:
            return doc
        if model is KnowledgeBase:
            return kb
        return None

    db.get = AsyncMock(side_effect=_get)

    exec_result = MagicMock()

    def _scalars_all():
        # 仅返回 Chunk 对象（Section 等不参与 chunk 查询）
        if added:
            return [o for o in added if o.__class__.__name__ == "Chunk"]
        return chunks or []

    exec_result.scalars.return_value.all.side_effect = _scalars_all
    exec_result.scalar_one_or_none.return_value = version
    db.execute = AsyncMock(return_value=exec_result)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _session_ctx(db):
    return MagicMock(
        __aenter__=AsyncMock(return_value=db),
        __aexit__=AsyncMock(return_value=None),
    )


def _make_parse_result():
    from app.rag.parser import ParsedPage, ParseResult

    return ParseResult(
        pages=[ParsedPage(page_number=1, content="第一页内容。第二页内容。", success=True)],
        total_pages=1,
        failed_pages=0,
        source_type="pdf",
    )


def _make_chunking_result(count=2):
    from app.rag.chunker import ChunkResult, ChunkingResult, SectionResult

    chunks = [
        ChunkResult(
            content=f"正文第 {i} 段",
            chunk_index=i,
            page_number=1,
            estimated_tokens=10,
            section_index=0,
            section_title="章节一",
            section_path="章节一",
        )
        for i in range(count)
    ]
    return ChunkingResult(
        sections=[
            SectionResult(
                title="章节一",
                path="章节一",
                level=1,
                start_offset=0,
                end_offset=100,
                start_chunk_index=0,
                end_chunk_index=count - 1,
            )
        ],
        chunks=chunks,
        total_chunks=count,
    )


def _make_embed_result(count=2):
    from tests.helpers import make_mock_embed_result

    return make_mock_embed_result(count)


def _chunks_from_db(db):
    """从 db.add 调用参数中抽取 Chunk 对象列表"""
    return [
        call[0][0] for call in db.add.call_args_list if call[0][0].__class__.__name__ == "Chunk"
    ]


# ==================== 幂等锁 ====================


class TestVersionLock:
    """Worker 以 Version UUID 为幂等键"""

    @pytest.mark.asyncio
    async def test_锁被占用_拒绝重复投递(self):
        doc = _make_doc()
        version = _make_version()
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch(
                "app.ingest.tasks.acquire_version_lock_async", return_value=False
            ) as mock_lock:
                from app.ingest.tasks import _ingest_version_async

                result = await _ingest_version_async(99)

        # 幂等键必须是 Version UUID，而非 doc_id
        mock_lock.assert_called_once_with("ver-uuid-1")
        assert result == {"status": "locked", "version_id": 99}


# ==================== 完整流水线 ====================


class TestVersionedFullPipeline:
    """queued → ... → ready 完整流水线"""

    @pytest.mark.asyncio
    async def test_完整流水线_发布成功(self):
        doc = _make_doc()
        version = _make_version(status="queued", version_no=1)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        mock_store = _make_stateful_store()
        staging_key = "uploads/staging/1/ver-uuid-1.json"

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch(
                        "app.ingest.tasks.parse_document", return_value=_make_parse_result()
                    ):
                        with patch(
                            "app.ingest.tasks.chunk_document", return_value=_make_chunking_result(2)
                        ):
                            with patch(
                                "app.ingest.tasks.embed_chunks",
                                AsyncMock(return_value=_make_embed_result(2)),
                            ):
                                with patch(
                                    "app.ingest.tasks.get_vector_store", return_value=mock_store
                                ):
                                    with patch(
                                        "app.ingest.tasks.write_staging_artifact",
                                        AsyncMock(return_value=staging_key),
                                    ):
                                        with patch(
                                            "app.ingest.versioning.invalidate_bm25_cache_async",
                                            AsyncMock(),
                                        ) as mock_invalidate:
                                            from app.ingest.tasks import _ingest_version_async

                                            result = await _ingest_version_async(99)

        assert result["status"] == "completed"
        # 终态
        assert version.status == "ready"
        assert version.published_at is not None
        assert doc.active_version == 1
        assert doc.status == DocumentStatus.COMPLETED
        # KB 发布锁
        assert kb.index_generation == 1
        assert kb.index_status == "ready"
        # BM25 失效
        mock_invalidate.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_chunk写入_携带版本与segment_uuid(self):
        doc = _make_doc()
        version = _make_version(status="queued", version_no=2, version_id=99)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        mock_store = _make_stateful_store()

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch(
                        "app.ingest.tasks.parse_document", return_value=_make_parse_result()
                    ):
                        with patch(
                            "app.ingest.tasks.chunk_document", return_value=_make_chunking_result(2)
                        ):
                            with patch(
                                "app.ingest.tasks.embed_chunks",
                                AsyncMock(return_value=_make_embed_result(2)),
                            ):
                                with patch(
                                    "app.ingest.tasks.get_vector_store", return_value=mock_store
                                ):
                                    with patch(
                                        "app.ingest.tasks.write_staging_artifact",
                                        AsyncMock(return_value="uploads/staging/1/ver-uuid-2.json"),
                                    ):
                                        with patch(
                                            "app.ingest.versioning.invalidate_bm25_cache_async",
                                            AsyncMock(),
                                        ):
                                            from app.ingest.tasks import _ingest_version_async

                                            await _ingest_version_async(99)

        chunks = _chunks_from_db(db)
        assert len(chunks) == 2
        for c in chunks:
            # Chunk 必须绑定 DocumentVersion 且带稳定 Segment UUID
            assert c.document_version_id == 99
            assert c.segment_uuid and len(c.segment_uuid) == 36
            # Chroma id 版本作用域：doc_{doc_id}_v{version}_c{chunk_index}
            assert c.chroma_id == f"doc_1_v2_c{c.chunk_index}"

    @pytest.mark.asyncio
    async def test_发布写入版本作用域向量(self):
        doc = _make_doc()
        version = _make_version(status="queued", version_no=3, version_id=99)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        mock_store = _make_stateful_store()

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch(
                        "app.ingest.tasks.parse_document", return_value=_make_parse_result()
                    ):
                        with patch(
                            "app.ingest.tasks.chunk_document", return_value=_make_chunking_result(2)
                        ):
                            with patch(
                                "app.ingest.tasks.embed_chunks",
                                AsyncMock(return_value=_make_embed_result(2)),
                            ):
                                with patch(
                                    "app.ingest.tasks.get_vector_store", return_value=mock_store
                                ):
                                    with patch(
                                        "app.ingest.tasks.write_staging_artifact",
                                        AsyncMock(return_value="uploads/staging/1/ver-uuid-3.json"),
                                    ):
                                        with patch(
                                            "app.ingest.versioning.invalidate_bm25_cache_async",
                                            AsyncMock(),
                                        ):
                                            from app.ingest.tasks import _ingest_version_async

                                            await _ingest_version_async(99)

        add_kwargs = mock_store.add.await_args.kwargs
        assert add_kwargs["ids"] == ["doc_1_v3_c0", "doc_1_v3_c1"]
        # 删除旧版本向量（doc_id 级 + version != 当前）
        # Chroma where 只允许顶层单个逻辑操作符，组合条件用 $and 包裹
        delete_kwargs = mock_store.delete.await_args.kwargs
        assert delete_kwargs["where"] == {
            "$and": [{"doc_id": 1}, {"version": {"$ne": 3}}],
        }


# ==================== 失败与恢复 ====================


class TestVersionedFailure:
    """不可恢复错误 → failed"""

    @pytest.mark.asyncio
    async def test_embedding失败_版本标记failed(self):
        doc = _make_doc()
        version = _make_version(status="embedding", version_no=1)
        kb = _make_kb()
        db = _make_db(doc, version, kb, chunks=_make_chunk_rows(2, version_no=1))

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch(
                        "app.ingest.tasks.embed_chunks",
                        AsyncMock(side_effect=RuntimeError("embed api down")),
                    ):
                        with patch("app.ingest.tasks.get_vector_store", return_value=AsyncMock()):
                            from app.ingest.tasks import _ingest_version_async

                            result = await _ingest_version_async(99)

        assert result["status"] == "failed"
        assert version.status == "failed"
        assert version.error_code == "EMBED_FAILED"
        assert "embed api down" in version.error_summary
        assert doc.status == DocumentStatus.FAILED

    @pytest.mark.asyncio
    async def test_文件路径为空_标记failed(self):
        doc = _make_doc()
        doc.file_path = None
        version = _make_version(status="queued", version_no=1)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    from app.ingest.tasks import _ingest_version_async

                    result = await _ingest_version_async(99)

        assert result["status"] == "failed"
        assert version.status == "failed"
        assert doc.status == DocumentStatus.FAILED
