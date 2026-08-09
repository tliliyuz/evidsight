"""Document v1 API 契约测试 — 对齐 API.md §6.2 与 docs/openapi/evidsight-v1.yaml。

验证 v1 端点的 method/路径/权限/成功状态码（202/200/204）/信封与错误码，
并断言响应 data 字段与 OpenAPI 组件 Schema 一致。上传/重试为异步 202 语义，
删除为 204 无正文；文档级操作通过 /api/v1/documents/{document_id} 定位，
不再依赖 legacy 的 {kb_id}/documents/{doc_uuid} 嵌套路径。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import DocumentNotFoundException, PermissionDeniedException
from app.models.enums import DocumentStatus
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentReprocessResponse,
    DocumentResponse,
    DocumentUploadResponse,
)

from tests.contract.openapi_utils import assert_data_matches_schema

VALID_KB_UUID = "550e8400-e29b-41d4-a716-446655440100"
VALID_DOC_UUID = "550e8400-e29b-41d4-a716-446655440200"
VALID_DOC_UUID_2 = "550e8400-e29b-41d4-a716-446655440201"
SEGMENT_UUID = "550e8400-e29b-41d4-a716-446655440300"
NOW = datetime.now(timezone.utc)


def _make_upload_response(filename="测试文档.pdf", file_type="pdf", status=DocumentStatus.QUEUED):
    return DocumentUploadResponse(
        uuid=VALID_DOC_UUID,
        kb_uuid=VALID_KB_UUID,
        filename=filename,
        file_type=file_type,
        file_size=1024,
        status=status,
    )


def _make_doc_response(filename="测试文档.pdf", status=DocumentStatus.COMPLETED):
    return DocumentResponse(
        uuid=VALID_DOC_UUID,
        kb_uuid=VALID_KB_UUID,
        filename=filename,
        file_type="pdf",
        file_size=1024,
        status=status,
        chunk_count=3,
        error_msg=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_list_data(total=1, page=1, page_size=20, items=None):
    if items is None:
        items = [_make_doc_response()]
    return DocumentListResponse(total=total, page=page, page_size=page_size, items=items)


def _make_chunks_data():
    return DocumentChunkListResponse(
        total=1,
        page=1,
        page_size=20,
        items=[
            DocumentChunkResponse(
                id=41,
                segment_id=SEGMENT_UUID,
                chunk_index=0,
                preview="安全预览内容",
                token_count=10,
                metadata={"page": 3},
            )
        ],
    )


class TestDocumentUploadV1:
    """POST /api/v1/knowledge-bases/{kb_id}/documents — 上传（202）"""

    URL = f"/api/v1/knowledge-bases/{VALID_KB_UUID}/documents"

    @pytest.mark.asyncio
    async def test_upload_success_202(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document_v1.upload_document", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_upload_response()

            response = await async_client.post(
                self.URL,
                files={"file": ("测试文档.pdf", b"%PDF-1.7 fake", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("DocumentUpload", body["data"])
        assert body["data"]["uuid"] == VALID_DOC_UUID
        assert body["data"]["status"] == "queued"
        # force 表单字段传递给 service（args: db, kb_id, user_id, role, file, force）
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.args[5] is False

    @pytest.mark.asyncio
    async def test_upload_force_true_passed(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document_v1.upload_document", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_upload_response()

            response = await async_client.post(
                self.URL,
                files={"file": ("测试文档.pdf", b"%PDF-1.7 fake", "application/pdf")},
                data={"force": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 202
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.args[5] is True

    @pytest.mark.asyncio
    async def test_upload_kb_not_found_404(self, async_client, auth_headers):
        with patch(
            "app.api.document_v1.resolve_uuid_to_id", new_callable=AsyncMock
        ) as mock_resolve:
            from app.core.exceptions import KnowledgeBaseNotFoundException

            mock_resolve.side_effect = KnowledgeBaseNotFoundException(VALID_KB_UUID)

            response = await async_client.post(
                self.URL,
                files={"file": ("t.pdf", b"%PDF", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["code"] == "E1001"

    @pytest.mark.asyncio
    async def test_upload_no_auth_401(self, async_client):
        response = await async_client.post(
            self.URL, files={"file": ("t.pdf", b"%PDF", "application/pdf")}
        )
        assert response.status_code == 401


class TestDocumentListV1:
    """GET /api/v1/knowledge-bases/{kb_id}/documents — 列表"""

    URL = f"/api/v1/knowledge-bases/{VALID_KB_UUID}/documents"

    @pytest.mark.asyncio
    async def test_list_success_200(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document_v1.list_documents", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_list_data()

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("DocumentList", body["data"])
        assert body["data"]["total"] == 1
        assert "uuid" in body["data"]["items"][0]
        assert "kb_uuid" in body["data"]["items"][0]

    @pytest.mark.asyncio
    async def test_list_status_filter_passed(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document_v1.list_documents", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_list_data(total=0, items=[])

            response = await async_client.get(
                f"{self.URL}?status=completed&filename=测试", headers=auth_headers
            )

        assert response.status_code == 200
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.kwargs["status"] == "completed"
        assert call_args.kwargs["filename"] == "测试"


class TestDocumentGetV1:
    """GET /api/v1/documents/{document_id} — 详情"""

    URL = f"/api/v1/documents/{VALID_DOC_UUID}"

    @pytest.mark.asyncio
    async def test_get_success_200(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.get_document", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)
            mock.return_value = _make_doc_response()

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("Document", body["data"])
        assert body["data"]["uuid"] == VALID_DOC_UUID
        assert body["data"]["status"] == "completed"
        # 通过 document uuid 反解出 kb_id 后调用 service
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.args[1] == 10

    @pytest.mark.asyncio
    async def test_get_not_found_404(self, async_client, auth_headers):
        with patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid:
            mock_uuid.side_effect = DocumentNotFoundException(VALID_DOC_UUID)

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["code"] == "E2001"

    @pytest.mark.asyncio
    async def test_get_permission_denied_403(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.get_document", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)
            mock.side_effect = PermissionDeniedException()

            response = await async_client.get(
                f"/api/v1/documents/{VALID_DOC_UUID_2}", headers=auth_headers
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"


class TestDocumentChunksV1:
    """GET /api/v1/documents/{document_id}/chunks — 分块列表"""

    URL = f"/api/v1/documents/{VALID_DOC_UUID}/chunks"

    @pytest.mark.asyncio
    async def test_chunks_success_200(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.get_document_chunks", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)
            mock.return_value = _make_chunks_data()

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("DocumentChunkList", body["data"])
        item = body["data"]["items"][0]
        # 稳定 Segment ID 契约：segment_id 为 location_id，旧 id 仅迁移期兼容
        assert item["segment_id"] == SEGMENT_UUID
        assert item["id"] == 41


class TestDocumentRetryV1:
    """POST /api/v1/documents/{document_id}/retry — 重新处理（202）"""

    URL = f"/api/v1/documents/{VALID_DOC_UUID}/retry"

    @pytest.mark.asyncio
    async def test_retry_success_202(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.reprocess_document", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)
            mock.return_value = DocumentReprocessResponse(
                doc_uuid=VALID_DOC_UUID, status=DocumentStatus.PARTIAL
            )

            response = await async_client.post(self.URL, headers=auth_headers)

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("DocumentReprocess", body["data"])
        assert body["data"]["doc_uuid"] == VALID_DOC_UUID


class TestDocumentDeleteV1:
    """DELETE /api/v1/documents/{document_id} — 删除（204 无正文）"""

    URL = f"/api/v1/documents/{VALID_DOC_UUID}"

    @pytest.mark.asyncio
    async def test_delete_success_204(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.delete_document", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)

            response = await async_client.delete(self.URL, headers=auth_headers)

        assert response.status_code == 204, response.text
        assert response.text == ""
        mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_permission_denied_403(self, async_client, auth_headers):
        with (
            patch("app.api.document_v1.get_by_uuid", new_callable=AsyncMock) as mock_uuid,
            patch("app.api.document_v1.delete_document", new_callable=AsyncMock) as mock,
        ):
            from app.models.document import Document

            mock_uuid.return_value = Document(id=1, kb_id=10, uuid=VALID_DOC_UUID)
            mock.side_effect = PermissionDeniedException()

            response = await async_client.delete(
                f"/api/v1/documents/{VALID_DOC_UUID_2}", headers=auth_headers
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"
