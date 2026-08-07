"""get_document_location Service 单元测试 — Mock DB session

对齐 API.md §6.2 / IDENTITY_AND_ACCESS §9：
- GET /api/v1/documents/{document_id}/locations/{location_id} 实时鉴权后返回最小片段和定位；
- 权限撤销、文档删除或来源失效返回明确受限/不可用状态；
- 仅返回 Document Active Version 下的 Segment 稳定身份（location_id == segment_uuid）。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.exceptions import (
    DocumentNotFoundException,
    EvidenceSourceUnavailableException,
    KnowledgeBaseNotFoundException,
    PermissionDeniedException,
)
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.knowledge_base import KnowledgeBase
from app.services.document_service import get_document_location

NOW = datetime.now(timezone.utc)

# 测试用稳定 ID
DOC_ID = 5
DOC_UUID = "doc-uuid-0001"
KB_ID = 1
KB_UUID = "kb-uuid-0001"
SEGMENT_UUID = "segment-uuid-0001"
VER_ID = 10
VER_UUID = "ver-uuid-0001"


def _make_scalar_one_or_none_result(value):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _make_kb(kb_id=KB_ID, user_id=1, status="active", visibility="private", kb_uuid=KB_UUID):
    kb = KnowledgeBase(
        id=kb_id,
        name="测试KB",
        user_id=user_id,
        status=status,
        visibility=visibility,
        chunk_count=0,
        doc_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    kb.uuid = kb_uuid
    return kb


def _make_doc(
    doc_id=DOC_ID,
    kb_id=KB_ID,
    status="completed",
    active_version=1,
    doc_uuid=DOC_UUID,
):
    doc = Document(
        id=doc_id,
        kb_id=kb_id,
        filename="test.pdf",
        file_type="pdf",
        status=status,
        chunk_count=10,
        file_size=1000,
        file_path=f"uploads/{kb_id}/{doc_id}/test.pdf",
        active_version=active_version,
        created_at=NOW,
        updated_at=NOW,
    )
    doc.uuid = doc_uuid
    return doc


def _make_version(ver_id=VER_ID, doc_id=DOC_ID, version=1, status="ready"):
    return DocumentVersion(
        id=ver_id,
        uuid=VER_UUID,
        document_id=doc_id,
        version=version,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        published_at=NOW,
    )


def _make_chunk(
    doc_id=DOC_ID,
    document_version_id=VER_ID,
    segment_uuid=SEGMENT_UUID,
    content="测试分块内容",
    metadata_=None,
):
    return Chunk(
        id=1,
        doc_id=doc_id,
        kb_id=KB_ID,
        document_version_id=document_version_id,
        segment_uuid=segment_uuid,
        chroma_id="c1",
        content=content,
        chunk_index=0,
        token_count=50,
        metadata_=metadata_,
    )


class TestGetDocumentLocation:
    """get_document_location — 实时鉴权 + 稳定身份解析 + 最小片段与定位"""

    @pytest.mark.asyncio
    async def test_成功返回页码定位(self, mock_db):
        """private KB owner：权限有效，返回 minimal_excerpt + page_number"""
        kb = _make_kb()
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(metadata_={"page": 3, "section_title": "背景"})
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),  # 查询文档
            _make_scalar_one_or_none_result(kb),  # check_kb_active → get_kb
            _make_scalar_one_or_none_result(chunk),  # 查询 segment
            _make_scalar_one_or_none_result(ver),  # 查询 Active Version
        ]

        result = await get_document_location(
            mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
        )

        assert result.document_id == DOC_UUID
        assert result.segment_id == SEGMENT_UUID
        assert result.minimal_excerpt == "测试分块内容"
        assert result.location == {"page_number": 3}
        assert result.source_updated_at is not None

    @pytest.mark.asyncio
    async def test_成功返回章节路径定位(self, mock_db):
        """public KB 非 owner：允许读取，无 page 时用 section_path 定位"""
        kb = _make_kb(user_id=99, visibility="public")
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(metadata_={"section_path": "第一章 > 背景"})
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        result = await get_document_location(
            mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=2, role="user"
        )

        assert result.location == {"section_path": ["第一章", "背景"]}

    @pytest.mark.asyncio
    async def test_文档不存在E2001(self, mock_db):
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(None),
        ]

        with pytest.raises(DocumentNotFoundException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2001"

    @pytest.mark.asyncio
    async def test_知识库不存在E1001(self, mock_db):
        doc = _make_doc()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(None),  # get_kb → 不存在
        ]

        with pytest.raises(KnowledgeBaseNotFoundException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E1001"

    @pytest.mark.asyncio
    async def test_知识库非active来源不可用E1001(self, mock_db):
        doc = _make_doc()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(_make_kb(status="deleting")),
        ]

        with pytest.raises(KnowledgeBaseNotFoundException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E1001"

    @pytest.mark.asyncio
    async def test_private非owner无权限E5005(self, mock_db):
        kb = _make_kb(user_id=99, visibility="private")
        doc = _make_doc()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
        ]

        with pytest.raises(PermissionDeniedException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=2, role="user"
            )
        assert exc.value.error_code == "E5005"

    @pytest.mark.asyncio
    async def test_admin可读取private非owner(self, mock_db):
        kb = _make_kb(user_id=99, visibility="private")
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(metadata_={"page": 1})
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        result = await get_document_location(
            mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=2, role="admin"
        )
        assert result.minimal_excerpt == "测试分块内容"

    @pytest.mark.asyncio
    async def test_segment不存在来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(None),  # segment 不存在
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_segment属于其他文档来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc()
        chunk = _make_chunk(doc_id=999, document_version_id=VER_ID)  # segment 不属于该文档
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_文档无active_version来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc(active_version=None)
        chunk = _make_chunk()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_segment不属于active_version来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(document_version_id=999)  # 不在 Active Version
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_version非ready来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc()
        ver = _make_version(status="failed")
        chunk = _make_chunk()
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_segment内容为空来源不可用E2015(self, mock_db):
        kb = _make_kb()
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(content="   ")
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"

    @pytest.mark.asyncio
    async def test_segment无位置来源不可用E2015(self, mock_db):
        """无 page 也无 section_path → 来源不可用，不伪造位置"""
        kb = _make_kb()
        doc = _make_doc()
        ver = _make_version()
        chunk = _make_chunk(metadata_={"section_title": "背景"})
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            _make_scalar_one_or_none_result(doc),
            _make_scalar_one_or_none_result(kb),
            _make_scalar_one_or_none_result(chunk),
            _make_scalar_one_or_none_result(ver),
        ]

        with pytest.raises(EvidenceSourceUnavailableException) as exc:
            await get_document_location(
                mock_db, doc_id=DOC_ID, location_id=SEGMENT_UUID, user_id=1, role="user"
            )
        assert exc.value.error_code == "E2015"
