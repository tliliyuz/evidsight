"""删除任务 worker 单元测试 — ChromaDB 向量清理 + 磁盘文件删除 + MySQL 物理删除

覆盖 _delete_document_async / _delete_kb_async 的幂等锁、失败分支与成功路径，
对齐 M2 稳定化退出门禁「文档入库、重处理、删除和失败恢复通过自动化与异常演练」。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest.delete_tasks import _delete_document_async, _delete_kb_async
from app.models.enums import DocumentStatus
from tests.helpers import make_mock_doc, mock_async_session_ctx, setup_mock_db


def _mock_store():
    """构造 mock 向量存储（delete 为 AsyncMock）"""
    store = AsyncMock()
    store.delete = AsyncMock()
    return store


# ==================== _delete_document_async ====================


class TestDeleteDocumentLock:
    """删除文档：幂等锁"""

    @pytest.mark.asyncio
    async def test_锁被占用_拒绝删除(self):
        with patch(
            "app.ingest.delete_tasks.acquire_idempotency_lock_async", AsyncMock(return_value=False)
        ):
            result = await _delete_document_async(1)
        assert result == {"status": "locked", "doc_id": 1}


class TestDeleteDocumentLoad:
    """删除文档：加载与状态校验"""

    @pytest.mark.asyncio
    async def test_文档不存在_返回not_found(self):
        db = setup_mock_db(doc=None)
        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    result = await _delete_document_async(1)
        assert result == {"status": "not_found", "doc_id": 1}

    @pytest.mark.asyncio
    async def test_状态非DELETING_跳过删除(self):
        doc = make_mock_doc(
            status=DocumentStatus.COMPLETED, file_path="/tmp/a.pdf", kb_id=1, doc_id=1
        )
        db = setup_mock_db(doc)
        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    result = await _delete_document_async(1)
        assert result["status"] == "skipped"


class TestDeleteDocumentVectorFailure:
    """删除文档：向量清理失败（失败关闭）"""

    @pytest.mark.asyncio
    async def test_向量清理失败_返回error(self):
        doc = make_mock_doc(
            status=DocumentStatus.DELETING, file_path="/tmp/a.pdf", kb_id=1, doc_id=1
        )
        db = setup_mock_db(doc)
        store = _mock_store()
        store.delete = AsyncMock(side_effect=RuntimeError("chroma down"))

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        result = await _delete_document_async(1)

        assert result["status"] == "error"
        assert "向量存储清理失败" in result["error"]
        # 失败关闭：不得继续磁盘删除或物理删除
        assert db.delete.await_count == 0


class TestDeleteDocumentDiskNonFatal:
    """删除文档：磁盘文件删除失败为非致命，继续物理删除"""

    @pytest.mark.asyncio
    async def test_磁盘删除失败_仍完成删除(self):
        doc = make_mock_doc(
            status=DocumentStatus.DELETING, file_path="/tmp/a.pdf", kb_id=1, doc_id=1
        )
        doc.chunk_count = 3
        db = setup_mock_db(doc)
        store = _mock_store()

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        with patch(
                            "app.ingest.delete_tasks.local_storage.delete",
                            AsyncMock(side_effect=OSError("permission")),
                        ):
                            with patch(
                                "app.ingest.delete_tasks.invalidate_bm25_cache_async", AsyncMock()
                            ):
                                result = await _delete_document_async(1)

        assert result["status"] == "completed"
        # 磁盘删除失败不阻断：向量清理 + MySQL 物理删除 + 缓存失效均执行
        store.delete.assert_awaited_once_with(kb_id=1, where={"doc_id": 1})
        assert db.delete.await_count == 1
        assert db.commit.await_count >= 1


class TestDeleteDocumentSuccess:
    """删除文档：成功路径 — 向量 + 磁盘 + 物理删除 + 缓存失效"""

    @pytest.mark.asyncio
    async def test_成功删除_清理向量与磁盘并更新kb计数(self):
        doc = make_mock_doc(
            status=DocumentStatus.DELETING, file_path="/tmp/a.pdf", kb_id=1, doc_id=1
        )
        doc.chunk_count = 3
        db = setup_mock_db(doc)
        store = _mock_store()

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        with patch("app.ingest.delete_tasks.local_storage.delete", AsyncMock()):
                            with patch(
                                "app.ingest.delete_tasks.invalidate_bm25_cache_async", AsyncMock()
                            ) as mock_bm25:
                                result = await _delete_document_async(1)

        assert result["status"] == "completed"
        store.delete.assert_awaited_once_with(kb_id=1, where={"doc_id": 1})
        db.delete.assert_awaited_once()
        mock_bm25.assert_awaited_once_with(1)


# ==================== _delete_kb_async ====================


class TestDeleteKbLock:
    """删除知识库：幂等锁"""

    @pytest.mark.asyncio
    async def test_锁被占用_拒绝删除(self):
        with patch(
            "app.ingest.delete_tasks.acquire_idempotency_lock_async", AsyncMock(return_value=False)
        ):
            result = await _delete_kb_async(1)
        assert result == {"status": "locked", "kb_id": 1}


class TestDeleteKbLoad:
    """删除知识库：加载与状态校验"""

    @pytest.mark.asyncio
    async def test_kb不存在_返回not_found(self):
        db = setup_mock_db(doc=None)
        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    result = await _delete_kb_async(1)
        assert result == {"status": "not_found", "kb_id": 1}

    @pytest.mark.asyncio
    async def test_kb状态非deleting_跳过删除(self):
        kb = MagicMock()
        kb.id = 1
        kb.status = "ready"
        db = setup_mock_db(kb)
        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    result = await _delete_kb_async(1)
        assert result["status"] == "skipped"


class TestDeleteKbVectorFailure:
    """删除知识库：collection 批量清理失败（失败关闭）"""

    @pytest.mark.asyncio
    async def test_collection清理失败_返回error(self):
        kb = MagicMock()
        kb.id = 1
        kb.status = "deleting"
        kb.name = "测试库"
        kb.uuid = "kb-uuid"
        db = setup_mock_db(kb)

        doc1 = MagicMock()
        doc1.id = 1
        doc1.file_path = "/tmp/a.pdf"
        db.execute.return_value.scalars.return_value.all.return_value = [doc1]

        store = _mock_store()
        store.delete = AsyncMock(side_effect=RuntimeError("collection down"))

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        result = await _delete_kb_async(1)

        assert result["status"] == "error"
        assert "向量存储批量清理失败" in result["error"]
        # 失败关闭：不得物理删除 KB
        assert db.delete.await_count == 0


class TestDeleteKbSuccess:
    """删除知识库：成功路径 — 全 collection 清理 + 逐文档磁盘删除 + 孤儿会话备份 + 物理删除"""

    @pytest.mark.asyncio
    async def test_成功删除_全collection清理并物理删除kb(self):
        kb = MagicMock()
        kb.id = 1
        kb.status = "deleting"
        kb.name = "测试库"
        kb.uuid = "kb-uuid"
        db = setup_mock_db(kb)

        doc1 = MagicMock()
        doc1.id = 1
        doc1.file_path = "/tmp/a.pdf"
        doc2 = MagicMock()
        doc2.id = 2
        doc2.file_path = None  # 无磁盘文件，跳过删除
        db.execute.return_value.scalars.return_value.all.return_value = [doc1, doc2]

        store = _mock_store()

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        with patch(
                            "app.ingest.delete_tasks.local_storage.delete", AsyncMock()
                        ) as mock_disk:
                            result = await _delete_kb_async(1)

        assert result["status"] == "completed"
        assert result["doc_count"] == 2
        # collection 级删除只调用一次；磁盘只删有路径的 doc1
        store.delete.assert_awaited_once_with(kb_id=1)
        mock_disk.assert_awaited_once_with("/tmp/a.pdf")
        # 物理删除 KB（第二次 async_session 中 db.delete）
        assert db.delete.await_count >= 1


class TestDeleteKbDiskNonFatal:
    """删除知识库：磁盘文件删除失败为非致命，继续物理删除"""

    @pytest.mark.asyncio
    async def test_磁盘删除失败_仍完成删除(self):
        kb = MagicMock()
        kb.id = 1
        kb.status = "deleting"
        kb.name = "测试库"
        kb.uuid = "kb-uuid"
        db = setup_mock_db(kb)

        doc1 = MagicMock()
        doc1.id = 1
        doc1.file_path = "/tmp/a.pdf"
        db.execute.return_value.scalars.return_value.all.return_value = [doc1]

        store = _mock_store()

        with patch(
            "app.ingest.delete_tasks.async_session", return_value=mock_async_session_ctx(db)
        ):
            with patch(
                "app.ingest.delete_tasks.acquire_idempotency_lock_async",
                AsyncMock(return_value=True),
            ):
                with patch("app.ingest.delete_tasks.release_idempotency_lock_async", AsyncMock()):
                    with patch("app.ingest.delete_tasks.get_vector_store", return_value=store):
                        with patch(
                            "app.ingest.delete_tasks.local_storage.delete",
                            AsyncMock(side_effect=OSError("permission")),
                        ):
                            result = await _delete_kb_async(1)

        assert result["status"] == "completed"
        assert db.delete.await_count >= 1
