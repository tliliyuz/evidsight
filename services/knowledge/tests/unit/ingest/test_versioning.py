"""版本化生命周期模块验收测试 — app.ingest.versioning

对齐 ADR-007 与 RAG_PIPELINE.md §3/§4.2：
- 每次入库/重处理创建独立 document_versions 记录，version 递增且唯一
- 对外 Document 状态映射固定：queued→queued、解析~验证→processing、
  ready→completed、ready_with_warnings→partial、failed→failed
- 发布使用 KB 短时锁（index_status=updating + index_generation++），
  切换 active_version → 删除旧版本向量 → 清理 staging → 恢复 ready
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest import versioning
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase


# ==================== 对外状态映射 ====================


class TestMapDocumentStatus:
    """版本状态 → 对外 Document 状态映射（ADR-007 固定映射）"""

    def test_queued_映射为_queued(self):
        assert versioning.map_document_status("queued") == DocumentStatus.QUEUED

    def test_解析阶段_映射为_processing(self):
        for stage in ("parsing", "chunking", "embedding", "indexing", "verifying"):
            assert versioning.map_document_status(stage) == DocumentStatus.PROCESSING

    def test_ready_映射为_completed(self):
        assert versioning.map_document_status("ready") == DocumentStatus.COMPLETED

    def test_ready_with_warnings_映射为_partial(self):
        assert versioning.map_document_status("ready_with_warnings") == DocumentStatus.PARTIAL

    def test_failed_映射为_failed(self):
        assert versioning.map_document_status("failed") == DocumentStatus.FAILED

    def test_未知状态_抛错(self):
        with pytest.raises(ValueError):
            versioning.map_document_status("mystery_stage")


# ==================== 版本号管理 ====================


class TestNextVersionNumber:
    """version 递增规则：max+1，无历史时从 1 开始"""

    @pytest.mark.asyncio
    async def test_无历史版本_返回1(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await versioning.next_version_number(db, doc_id=1) == 1

    @pytest.mark.asyncio
    async def test_已有版本_返回max加1(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = 3
        db.execute = AsyncMock(return_value=result)

        assert await versioning.next_version_number(db, doc_id=1) == 4


class TestCreateDocumentVersion:
    """create_document_version 创建 queued 版本并重置文档状态"""

    @pytest.mark.asyncio
    async def test_创建版本_设置uuid与queued状态(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        # 无历史版本 → version=1
        exec_result = MagicMock()
        exec_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        doc = MagicMock(spec=Document)
        doc.id = 10
        doc.status = None

        version = await versioning.create_document_version(db, doc, source="upload")

        assert version.document_id == 10
        assert version.version == 1
        assert version.status == "queued"
        assert len(version.uuid) == 36  # UUID4
        assert doc.status == DocumentStatus.QUEUED
        db.add.assert_called_once_with(version)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_第二次创建_版本递增(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar.return_value = 2
        db.execute = AsyncMock(return_value=exec_result)

        doc = MagicMock(spec=Document)
        doc.id = 10
        doc.status = None

        version = await versioning.create_document_version(db, doc)

        assert version.version == 3


class TestUpdateVersion:
    """update_version 写入阶段 Checkpoint 字段"""

    @pytest.mark.asyncio
    async def test_更新字段_并提交(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        version = MagicMock(spec=DocumentVersion)
        version.last_success_batch = None

        await versioning.update_version(
            db, version,
            status="embedding",
            last_success_batch=2,
            expected_segment_count=10,
        )

        assert version.status == "embedding"
        assert version.last_success_batch == 2
        assert version.expected_segment_count == 10
        db.commit.assert_called_once()


class TestGetPendingVersion:
    """get_pending_version 返回最新非终态版本；全终态返回 None"""

    @pytest.mark.asyncio
    async def test_返回最新非终态版本(self):
        db = AsyncMock()
        version = MagicMock(spec=DocumentVersion)
        version.status = "embedding"
        result = MagicMock()
        result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=result)

        doc = MagicMock(spec=Document)
        doc.id = 1
        assert await versioning.get_pending_version(db, doc) is version

    @pytest.mark.asyncio
    async def test_全终态_返回None(self):
        db = AsyncMock()
        version = MagicMock(spec=DocumentVersion)
        version.status = "ready"
        result = MagicMock()
        result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=result)

        doc = MagicMock(spec=Document)
        doc.id = 1
        assert await versioning.get_pending_version(db, doc) is None


# ==================== 原子发布 ====================


def _make_staging_rows(count: int = 2):
    return [
        {
            "segment_uuid": f"seg-{i}",
            "chunk_index": i,
            "content": f"内容 {i}",
            "embedding": [0.1] * 8,
            "metadata": {"page": i + 1},
        }
        for i in range(count)
    ]


class TestPublishVersion:
    """发布：KB 锁 → 写向量 → 切换 active_version → 删旧向量 → 清理 staging → ready"""

    @pytest.mark.asyncio
    async def test_发布_按ADR顺序执行(self):
        db = AsyncMock()

        kb = MagicMock(spec=KnowledgeBase)
        kb.id = 1
        kb.index_status = "ready"
        kb.index_generation = 0
        kb.status = "active"

        doc = MagicMock(spec=Document)
        doc.id = 7
        doc.active_version = None
        doc.status = None

        version = MagicMock(spec=DocumentVersion)
        version.id = 99
        version.version = 2
        version.status = "verifying"
        version.published_at = None
        version.staging_artifact_key = "staging/1/ver-uuid.json"

        store = AsyncMock()
        store.get_ids = AsyncMock(return_value=["doc_7_v2_c0", "doc_7_v2_c1"])
        rows = _make_staging_rows(2)

        # 记录每次 commit 时 KB 的发布锁状态，验证「updating → ready」的锁窗口
        status_log: list[str] = []

        def _record_commit(*args, **kwargs):
            status_log.append(kb.index_status)

        db.commit = AsyncMock(side_effect=_record_commit)

        with patch.object(versioning.local_storage, "delete", AsyncMock()) as mock_fs_delete:
            with patch("app.ingest.versioning.invalidate_bm25_cache_async",
                       AsyncMock()) as mock_invalidate:
                await versioning.publish_version(db, kb, doc, version, store, rows)

        # 1. KB 短时锁：进入 updating，最终恢复 ready
        assert "updating" in status_log
        assert status_log[-1] == "ready"
        assert kb.index_generation == 1

        # 2. 版本作用域向量写入
        call_ids = store.add.await_args.kwargs["ids"]
        assert call_ids == ["doc_7_v2_c0", "doc_7_v2_c1"]
        meta = store.add.await_args.kwargs["metadatas"]
        assert meta[0]["doc_id"] == 7
        assert meta[0]["version"] == 2

        # 3. MySQL 事务切换 active_version + 版本终态
        assert doc.active_version == 2
        assert version.status == "ready"
        assert version.published_at is not None
        assert doc.status == DocumentStatus.COMPLETED

        # 4. 删除旧版本向量（非当前 version）
        # Chroma where 只允许顶层单个逻辑操作符，组合条件必须用 $and 包裹
        # （实测 ChromaDB 0.5.23 对扁平双键 where 抛 "exactly one operator"）
        delete_kwargs = store.delete.await_args.kwargs
        assert delete_kwargs["kb_id"] == 1
        assert delete_kwargs["where"] == {
            "$and": [{"doc_id": 7}, {"version": {"$ne": 2}}],
        }

        # 5. 清理 staging 产物
        mock_fs_delete.assert_called_once_with("staging/1/ver-uuid.json")

        # 6. KB 恢复 ready + BM25 失效
        assert kb.index_status == "ready"
        mock_invalidate.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_发布_ready_with_warnings_映射partial(self):
        db = AsyncMock()
        kb = MagicMock(spec=KnowledgeBase)
        kb.id = 1
        kb.index_status = "ready"
        kb.index_generation = 0
        kb.status = "active"
        doc = MagicMock(spec=Document)
        doc.id = 7
        doc.active_version = None
        doc.status = None
        version = MagicMock(spec=DocumentVersion)
        version.id = 99
        version.version = 1
        version.status = "ready_with_warnings"
        version.published_at = None
        version.staging_artifact_key = None
        store = AsyncMock()
        store.get_ids = AsyncMock(return_value=["doc_7_v1_c0"])

        with patch("app.ingest.versioning.invalidate_bm25_cache_async", AsyncMock()):
            await versioning.publish_version(db, kb, doc, version, store, _make_staging_rows(1))

        assert doc.status == DocumentStatus.PARTIAL
        assert doc.active_version == 1

    @pytest.mark.asyncio
    async def test_发布_kb删除中_中止并标记版本失败(self):
        # ADR-007：deleting 状态不发布；置 version failed 并抛 PublishAbortedError
        db = AsyncMock()
        db.commit = AsyncMock()
        kb = MagicMock(spec=KnowledgeBase)
        kb.id = 1
        kb.status = "deleting"
        kb.index_status = "deleting"
        kb.index_generation = 0
        doc = MagicMock(spec=Document)
        doc.id = 7
        doc.active_version = None
        doc.status = None
        version = MagicMock(spec=DocumentVersion)
        version.id = 99
        version.version = 2
        version.status = "verifying"
        version.published_at = None
        version.staging_artifact_key = None
        version.error_msg = None
        store = AsyncMock()

        with pytest.raises(versioning.PublishAbortedError):
            await versioning.publish_version(db, kb, doc, version, store, _make_staging_rows(2))

        assert version.status == "failed"
        assert version.error_msg == "知识库或文档处于删除流程，发布中止"
        store.add.assert_not_called()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_发布_在线集合不一致_进入recovering(self):
        # ADR-007「校验在线集合」：发布后新版本向量缺失 → 抛异常并进入 recovering
        db = AsyncMock()
        kb = MagicMock(spec=KnowledgeBase)
        kb.id = 1
        kb.index_status = "ready"
        kb.index_generation = 0
        kb.status = "active"
        doc = MagicMock(spec=Document)
        doc.id = 7
        doc.active_version = None
        doc.status = None
        version = MagicMock(spec=DocumentVersion)
        version.id = 99
        version.version = 2
        version.status = "verifying"
        version.published_at = None
        version.staging_artifact_key = None
        store = AsyncMock()
        # 在线集合只含 c0，缺 c1
        store.get_ids = AsyncMock(return_value=["doc_7_v2_c0"])

        with patch.object(versioning.local_storage, "delete", AsyncMock()):
            with pytest.raises(Exception):
                await versioning.publish_version(db, kb, doc, version, store, _make_staging_rows(2))

        assert kb.index_status == "recovering"


# ==================== chunk_count 重算语义（P1） ====================


class TestCountChunks:
    """发布计数重算：只统计 Active Version 覆盖的 chunks（对齐 ADR-007）"""

    @pytest.mark.asyncio
    async def test_count_active_version_chunks_返回scalar(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = 42
        db.execute = AsyncMock(return_value=result)

        assert await versioning.count_active_version_chunks(db, kb_id=1) == 42

    @pytest.mark.asyncio
    async def test_count_version_chunks_返回scalar(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = 7
        db.execute = AsyncMock(return_value=result)

        assert await versioning.count_version_chunks(db, version_id=99) == 7
