"""Celery 版本化入库流水线任务测试 — 兼容桥 / 分块持久化 / Checkpoint / Clean 接线

对齐 ADR-007 / RAG_PIPELINE.md §3/§4.2：
- ingest_document 作为兼容桥接：查找 pending version → 投递 ingest_version
- Chunk 写入携带 document_version_id + 稳定 Segment UUID
- last_success_batch 以 Version 为载体的批次级 checkpoint
- Clean 阶段接线：parse 之后、chunk 之前清洗页面结构
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest.tasks import (
    _ingest_document_async,
    _replace_sections_and_chunks,
)
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.rag.chunker import ChunkResult, ChunkingResult, SectionResult
from tests.helpers import make_mock_embed_result


def _make_version(status="queued", version_no=1, version_id=99):
    v = MagicMock(spec=DocumentVersion)
    v.id = version_id
    v.uuid = f"ver-uuid-{version_no}"
    v.document_id = 1
    v.version = version_no
    v.status = status
    v.last_success_batch = 0
    v.expected_segment_count = None
    v.embedded_segment_count = None
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
    d.status = DocumentStatus.QUEUED
    d.active_version = None
    d.chunk_count = 0
    d.error_msg = None
    return d


def _make_kb():
    kb = MagicMock(spec=KnowledgeBase)
    kb.id = 1
    kb.index_status = "ready"
    kb.index_generation = 0
    kb.chunk_count = 0
    kb.doc_count = 0
    return kb


def _make_db(doc, version, kb, chunks=None):
    """状态化 AsyncSession mock：execute 返回新增的 Chunk 对象。"""
    db = AsyncMock()
    added: list = []

    def _add(obj):
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


def _make_chunking_result(chunk_count: int = 3):
    return ChunkingResult(
        sections=[
            SectionResult(
                title="第一章", path="第一章", level=1,
                start_offset=0, end_offset=100,
                start_chunk_index=0, end_chunk_index=chunk_count - 1,
            )
        ],
        chunks=[
            ChunkResult(
                content=f"正文第 {i} 段",
                chunk_index=i,
                page_number=1,
                estimated_tokens=5,
                section_index=0,
                section_title="第一章",
                section_path="第一章",
            )
            for i in range(chunk_count)
        ],
        total_chunks=chunk_count,
    )


def _make_parse_result():
    from app.rag.parser import ParsedPage, ParseResult

    return ParseResult(
        pages=[ParsedPage(page_number=1, content="第一页正文内容", success=True)],
        total_pages=1,
        failed_pages=0,
        source_type="pdf",
    )


# ==================== 兼容桥接 ====================


class TestCompatBridge:
    """ingest_document 兼容桥：查找 pending version → 投递 ingest_version"""

    @pytest.mark.asyncio
    async def test_有pending版本_投递ingest_version(self):
        doc = _make_doc()
        version = _make_version(status="queued", version_no=2, version_id=99)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks._ingest_version_async",
                       AsyncMock(return_value={"status": "locked", "version_id": 99})) as mock_ingest:
                result = await _ingest_document_async(1)

        assert result == {"status": "locked", "version_id": 99}
        mock_ingest.assert_called_once_with(99)

    @pytest.mark.asyncio
    async def test_无pending版本_返回no_pending_version(self):
        doc = _make_doc()
        # 全部终态 → get_pending_version 返回 None
        version = _make_version(status="ready", version_no=1)
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks._ingest_version_async",
                       AsyncMock()) as mock_ingest:
                result = await _ingest_document_async(1)

        assert result == {"status": "no_pending_version", "doc_id": 1}
        mock_ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_文档已删除_返回deleting(self):
        doc = _make_doc()
        doc.status = DocumentStatus.DELETING
        version = _make_version()
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            result = await _ingest_document_async(1)

        assert result == {"status": "deleting", "doc_id": 1}


# ==================== 分块持久化 ====================


class TestSectionPersistence:
    """PR2 章节与分块写入测试（版本化）"""

    @pytest.mark.asyncio
    async def test_replace_sections_and_chunks_携带版本与segment_uuid(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        added_sections = []
        added_chunks = []

        def _add(obj):
            if obj.__class__.__name__ == "Section":
                obj.id = 100 + len(added_sections)
                added_sections.append(obj)
            elif obj.__class__.__name__ == "Chunk":
                added_chunks.append(obj)

        # session.add 是同步调用，必须用 MagicMock 才能触发 side_effect
        db.add = MagicMock(side_effect=_add)

        version = _make_version(version_no=2, version_id=99)
        chunking_result = _make_chunking_result(3)

        await _replace_sections_and_chunks(
            db, doc_id=1, kb_id=2, chunking_result=chunking_result, version=version
        )

        assert db.execute.await_count == 2
        assert len(added_sections) == 1
        assert len(added_chunks) == 3
        assert added_sections[0].document_version_id == 99
        for c in added_chunks:
            assert c.document_version_id == 99
            assert c.segment_uuid and len(c.segment_uuid) == 36
            assert c.chroma_id == f"doc_1_v2_c{c.chunk_index}"
            assert c.section_id == 100


# ==================== Checkpoint ====================


class TestVersionBatchCheckpoint:
    """last_success_batch 以 Version 为载体的批次级 checkpoint + 增量 staging 恢复"""

    @pytest.mark.asyncio
    async def test_embedding续传_从last_success_batch继续(self):
        doc = _make_doc()
        version = _make_version(status="embedding", version_no=1)
        version.last_success_batch = 1
        version.staging_artifact_key = "uploads/staging/1/ver-uuid-1.json"
        kb = _make_kb()

        # 4 chunks, batch_size=2 → 2 batches；last_success_batch=1 → 只处理 batch 1
        from unittest.mock import MagicMock as _MM

        chunk_rows = []
        for i in range(4):
            c = _MM()
            c.id = 200 + i
            c.chunk_index = i
            c.content = f"chunk {i}"
            c.chroma_id = f"doc_1_v1_c{i}"
            c.section_id = 50 + i
            c.metadata_ = {"section_title": "", "section_path": ""}
            c.segment_uuid = f"00000000-0000-0000-0000-{i:012d}"
            c.document_version_id = 99
            chunk_rows.append(c)

        # 已有部分 staging 产物：chunk 0/1 已嵌入（batch 0 完成）
        partial_rows = [
            {
                "segment_uuid": f"00000000-0000-0000-0000-{i:012d}",
                "chunk_index": i,
                "content": f"chunk {i}",
                "embedding": [0.1] * 8,
                "metadata": {"section_title": "", "section_path": ""},
            }
            for i in range(2)
        ]

        db = _make_db(doc, version, kb, chunks=chunk_rows)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    mock_embed = AsyncMock(return_value=make_mock_embed_result(2))
                    with patch("app.ingest.tasks.embed_chunks", mock_embed):
                        with patch("app.ingest.tasks.get_vector_store", return_value=AsyncMock()):
                            with patch("app.ingest.tasks.read_staging_artifact",
                                      AsyncMock(return_value=partial_rows)):
                                with patch("app.ingest.tasks.settings") as mock_settings:
                                    mock_settings.EMBED_BATCH_SIZE = 2
                                    mock_settings.CHROMA_BATCH_SIZE = 20
                                    with patch("app.ingest.tasks.write_staging_artifact",
                                              AsyncMock(return_value="uploads/staging/1/ver-uuid-1.json")):
                                        with patch("app.ingest.versioning.invalidate_bm25_cache_async",
                                                   AsyncMock()):
                                            from app.ingest.tasks import _ingest_version_async
                                            result = await _ingest_version_async(99)

        assert result["status"] == "completed"
        # 从 batch 1 续传 → 只调用 1 次 embedding（batch 0 已在产物中）
        assert mock_embed.call_count == 1
        # checkpoint 推进到 2（全部完成）
        assert version.last_success_batch == 2


# ==================== Clean 阶段接线 ====================


class TestCleanStageWiring:
    """Clean 阶段接线：parse 之后、chunk 之前清洗页面结构（对齐 RAG_PIPELINE.md §4.1）"""

    def _noisy_parse_result(self):
        """含页号行 + mojibake 的解析结果（模拟真实 PDF 提取噪声）"""
        from app.rag.parser import ParsedPage, ParseResult

        return ParseResult(
            pages=[ParsedPage(page_number=1, content="42\ncafÃ©  正文内容", success=True)],
            total_pages=1,
            failed_pages=0,
            source_type="pdf",
        )

    @pytest.mark.asyncio
    async def test_CLEAN启用_先清洗再进入分块(self):
        from app.rag.cleaner import clean_parse_result as _real_clean

        doc = _make_doc()
        version = _make_version()
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        captured = {}

        def _capture_chunk(full_text, pages):
            captured["full_text"] = full_text
            return _make_chunking_result(2)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch("app.ingest.tasks.parse_document", return_value=self._noisy_parse_result()):
                        with patch("app.ingest.tasks.clean_parse_result", wraps=_real_clean) as mock_clean:
                            with patch("app.ingest.tasks.chunk_document", side_effect=_capture_chunk):
                                with patch("app.ingest.tasks.embed_chunks",
                                          AsyncMock(return_value=make_mock_embed_result(2))):
                                    with patch("app.ingest.tasks.get_vector_store", return_value=AsyncMock()):
                                        with patch("app.ingest.tasks.write_staging_artifact",
                                                  AsyncMock(return_value="uploads/staging/1/ver-uuid-1.json")):
                                            with patch("app.ingest.versioning.invalidate_bm25_cache_async",
                                                       AsyncMock()):
                                                from app.ingest.tasks import _ingest_version_async
                                                result = await _ingest_version_async(99)

        assert result["status"] == "completed"
        mock_clean.assert_called_once()
        assert mock_clean.call_args.kwargs["strip_boilerplate"] is True
        assert mock_clean.call_args.kwargs["normalize_space"] is True
        assert mock_clean.call_args.kwargs["repair_unicode"] is True
        assert "42" not in captured["full_text"]
        assert "café" in captured["full_text"]

    @pytest.mark.asyncio
    async def test_CLEAN关闭_原样进入分块(self):
        doc = _make_doc()
        version = _make_version()
        kb = _make_kb()
        db = _make_db(doc, version, kb)

        captured = {}

        def _capture_chunk(full_text, pages):
            captured["full_text"] = full_text
            return _make_chunking_result(2)

        with patch("app.ingest.tasks.async_session", return_value=_session_ctx(db)):
            with patch("app.ingest.tasks.acquire_version_lock_async", return_value=True):
                with patch("app.ingest.tasks.release_version_lock_async"):
                    with patch("app.ingest.tasks.parse_document", return_value=self._noisy_parse_result()):
                        with patch("app.ingest.tasks.settings.CLEAN_ENABLED", False):
                            with patch("app.ingest.tasks.chunk_document", side_effect=_capture_chunk):
                                with patch("app.ingest.tasks.embed_chunks",
                                          AsyncMock(return_value=make_mock_embed_result(2))):
                                    with patch("app.ingest.tasks.get_vector_store", return_value=AsyncMock()):
                                        with patch("app.ingest.tasks.write_staging_artifact",
                                                  AsyncMock(return_value="uploads/staging/1/ver-uuid-1.json")):
                                            with patch("app.ingest.versioning.invalidate_bm25_cache_async",
                                                       AsyncMock()):
                                                from app.ingest.tasks import _ingest_version_async
                                                result = await _ingest_version_async(99)

        assert result["status"] == "completed"
        assert "42" in captured["full_text"]
        assert "cafÃ©" in captured["full_text"]
