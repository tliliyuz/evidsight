"""GET /api/v1/documents/{document_id}/locations/{location_id} API 测试

对齐 API.md §6.2：实时鉴权后返回最小片段和定位（信封迁移态 {"code","message","data"}）。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import (
    DocumentNotFoundException,
    EvidenceSourceUnavailableException,
    PermissionDeniedException,
)
from app.schemas.document import DocumentLocationResponse

DOC_UUID = "22222222-2222-4222-8222-222222222222"
DOC_UUID_999 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
LOCATION_UUID = "44444444-4444-4444-8444-444444444444"
NOW = datetime.now(timezone.utc)


def _make_location_response():
    return DocumentLocationResponse(
        document_id=DOC_UUID,
        segment_id=LOCATION_UUID,
        minimal_excerpt="来源最小片段",
        location={"page_number": 3},
        source_updated_at=NOW,
    )


class TestGetDocumentLocationV1:
    """GET /api/v1/documents/{document_id}/locations/{location_id}"""

    @pytest.mark.asyncio
    async def test_成功返回最小片段和定位(self, async_client, auth_headers):
        """A: 有效 document_id + location_id → 200 信封 + data 最小片段和定位"""
        with (
            patch("app.api.document.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document.get_document_location", new_callable=AsyncMock) as mock_get,
        ):
            mock_resolve.return_value = 5
            mock_get.return_value = _make_location_response()

            response = await async_client.get(
                f"/api/v1/documents/{DOC_UUID}/locations/{LOCATION_UUID}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "0"
        assert body["message"] == "ok"
        data = body["data"]
        assert data["document_id"] == DOC_UUID
        assert data["segment_id"] == LOCATION_UUID
        assert data["minimal_excerpt"] == "来源最小片段"
        assert data["location"] == {"page_number": 3}
        assert "source_updated_at" in data

    @pytest.mark.asyncio
    async def test_文档不存在E2001(self, async_client, auth_headers):
        """文档不存在 → 404 E2001"""
        with (
            patch("app.api.document.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document.get_document_location", new_callable=AsyncMock) as mock_get,
        ):
            mock_resolve.side_effect = DocumentNotFoundException(DOC_UUID_999)
            mock_get.return_value = _make_location_response()

            response = await async_client.get(
                f"/api/v1/documents/{DOC_UUID_999}/locations/{LOCATION_UUID}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["code"] == "E2001"
        mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_无权限E5005(self, async_client, auth_headers):
        """无 READ 权限 → 403 E5005"""
        with (
            patch("app.api.document.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document.get_document_location", new_callable=AsyncMock) as mock_get,
        ):
            mock_resolve.return_value = 5
            mock_get.side_effect = PermissionDeniedException()

            response = await async_client.get(
                f"/api/v1/documents/{DOC_UUID}/locations/{LOCATION_UUID}",
                headers=auth_headers,
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"

    @pytest.mark.asyncio
    async def test_来源不可用E2015(self, async_client, auth_headers):
        """来源失效（segment 非 Active Version/无内容/无位置）→ 404 E2015"""
        with (
            patch("app.api.document.resolve_uuid_to_id", new_callable=AsyncMock) as mock_resolve,
            patch("app.api.document.get_document_location", new_callable=AsyncMock) as mock_get,
        ):
            mock_resolve.return_value = 5
            mock_get.side_effect = EvidenceSourceUnavailableException("来源不可用")

            response = await async_client.get(
                f"/api/v1/documents/{DOC_UUID}/locations/{LOCATION_UUID}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["code"] == "E2015"

    @pytest.mark.asyncio
    async def test_未登录E5004(self, async_client):
        """未携带 Bearer → 401 E5004"""
        response = await async_client.get(f"/api/v1/documents/{DOC_UUID}/locations/{LOCATION_UUID}")
        assert response.status_code == 401
        assert response.json()["code"] == "E5004"
