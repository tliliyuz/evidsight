"""恢复扫描验收测试 — app.ingest.recovery_tasks._scan_stuck_versions_async

对齐 ADR-007 / RAG_PIPELINE.md §3.4：
- 非终态版本超 STUCK_VERSION_TIMEOUT 且无活跃锁 → 重新投递 ingest_version
- 有活跃锁（worker 正在处理）→ 不重投，避免重复消费
- index_status 处于 updating/recovering 超 KB_LOCK_TIMEOUT → 回滚 ready
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest.recovery_tasks import _scan_stuck_versions_async


def _old_dt(seconds=9999) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _make_version(version_id=1, status="embedding", uuid="ver-uuid-1"):
    v = MagicMock()
    v.id = version_id
    v.uuid = uuid
    v.status = status
    v.updated_at = _old_dt()
    return v


def _make_kb(kb_id=10, index_status="updating"):
    kb = MagicMock()
    kb.id = kb_id
    kb.index_status = index_status
    kb.updated_at = _old_dt()
    return kb


def _mock_session_pair(version_rows, kb_rows):
    """按序返回两个 async_session() 上下文：首个查版本，次个查 KB。"""
    db1 = AsyncMock()
    res1 = MagicMock()
    res1.scalars.return_value.all.return_value = list(version_rows)
    db1.execute = AsyncMock(return_value=res1)

    db2 = AsyncMock()
    res2 = MagicMock()
    res2.scalars.return_value.all.return_value = list(kb_rows)
    db2.execute = AsyncMock(return_value=res2)
    db2.commit = AsyncMock()

    def _cm(db):
        return MagicMock(
            __aenter__=AsyncMock(return_value=db),
            __aexit__=AsyncMock(return_value=None),
        )

    return db1, db2, [_cm(db1), _cm(db2)]


class TestScanStuckVersions:
    """卡死版本重投递"""

    @pytest.mark.asyncio
    async def test_卡死版本无锁_重新投递ingest_version(self):
        version = _make_version(version_id=7, status="embedding")
        db1, db2, cm_list = _mock_session_pair([version], [])
        async_session = MagicMock(side_effect=cm_list)

        with patch("app.ingest.recovery_tasks.async_session", async_session):
            with patch("app.ingest.recovery_tasks.acquire_version_lock_async",
                       AsyncMock(return_value=True)) as mock_acquire:
                with patch("app.ingest.recovery_tasks.release_version_lock_async",
                           AsyncMock()) as mock_release:
                    with patch("app.ingest.recovery_tasks.ingest_version") as mock_task:
                        result = await _scan_stuck_versions_async()

        assert result["stuck_versions"] == 1
        assert result["redispatched"] == 1
        mock_acquire.assert_called_once_with("ver-uuid-1")
        mock_release.assert_called_once_with("ver-uuid-1")
        mock_task.delay.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_卡死版本有活跃锁_不重投(self):
        version = _make_version(version_id=7, status="embedding")
        db1, db2, cm_list = _mock_session_pair([version], [])
        async_session = MagicMock(side_effect=cm_list)

        with patch("app.ingest.recovery_tasks.async_session", async_session):
            with patch("app.ingest.recovery_tasks.acquire_version_lock_async",
                       AsyncMock(return_value=False)):
                with patch("app.ingest.recovery_tasks.ingest_version") as mock_task:
                    result = await _scan_stuck_versions_async()

        assert result["redispatched"] == 0
        mock_task.delay.assert_not_called()

    def test_终态不在处理阶段集合(self):
        """扫描 SQL 只命中 PROCESSING_STAGES；终态必须与处理阶段集合无交集。

        （SQL WHERE 过滤无法在 mock 层模拟，这里验证集合语义保证终态不被扫描）
        """
        from app.ingest.versioning import (
            PROCESSING_STAGES,
            TERMINAL_VERSION_STATUSES,
        )

        assert not (PROCESSING_STAGES & TERMINAL_VERSION_STATUSES)


class TestScanStuckKbLock:
    """卡死 KB 发布锁回滚"""

    @pytest.mark.asyncio
    async def test_updating超时_回滚ready(self):
        kb = _make_kb(kb_id=10, index_status="updating")
        db1, db2, cm_list = _mock_session_pair([], [kb])
        async_session = MagicMock(side_effect=cm_list)

        with patch("app.ingest.recovery_tasks.async_session", async_session):
            result = await _scan_stuck_versions_async()

        assert result["stuck_kbs"] == 1
        assert kb.index_status == "ready"
        db2.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recovering超时_回滚ready(self):
        kb = _make_kb(kb_id=10, index_status="recovering")
        db1, db2, cm_list = _mock_session_pair([], [kb])
        async_session = MagicMock(side_effect=cm_list)

        with patch("app.ingest.recovery_tasks.async_session", async_session):
            result = await _scan_stuck_versions_async()

        assert result["stuck_kbs"] == 1
        assert kb.index_status == "ready"

    def test_ready不在卡死状态集合(self):
        """扫描 SQL 只命中 updating/recovering；ready 必须不在其中。

        （SQL WHERE 过滤无法在 mock 层模拟，这里验证集合语义保证 ready 不被回滚）
        """
        from app.ingest.recovery_tasks import _KB_LOCK_STATUSES

        assert "ready" not in _KB_LOCK_STATUSES
        assert set(_KB_LOCK_STATUSES) == {"updating", "recovering"}

    @pytest.mark.asyncio
    async def test_无卡死_返回全零统计(self):
        db1, db2, cm_list = _mock_session_pair([], [])
        async_session = MagicMock(side_effect=cm_list)

        with patch("app.ingest.recovery_tasks.async_session", async_session):
            result = await _scan_stuck_versions_async()

        assert result == {"stuck_versions": 0, "redispatched": 0, "stuck_kbs": 0}
