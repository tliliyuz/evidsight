"""Knowledge Base v1 API 契约测试 — 对齐 API.md §6.1 与 docs/openapi/evidsight-v1.yaml。

验证 v1 端点的 method/路径/权限/成功状态码（201/200/204）/信封与错误码，
并断言响应 data 字段与 OpenAPI 组件 Schema 一致。统一可见列表的行为语义
（scope 并集、分页去重、搜索）由 tests/unit/services/test_kb_list_visible.py
在真实库上验证，本文件只验证 Provider 层契约。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import (
    KnowledgeBaseNotFoundException,
    PermissionDeniedException,
)
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseListResponse, KnowledgeBaseResponse

from tests.contract.openapi_utils import assert_data_matches_schema

VALID_KB_UUID = "550e8400-e29b-41d4-a716-446655440100"
VALID_KB_UUID_2 = "550e8400-e29b-41d4-a716-446655440101"
NOW = datetime.now(timezone.utc)


def _platform_uuid(i: int) -> str:
    return f"550e8400-e29b-41d4-a716-4466554400{i:02d}"


def _make_kb_response(
    kb_uuid=VALID_KB_UUID,
    name="测试知识库",
    description=None,
    owner=_platform_uuid(1),
    status="active",
    visibility="private",
    doc_count=0,
    chunk_count=0,
):
    return KnowledgeBaseResponse(
        uuid=kb_uuid,
        name=name,
        description=description,
        owner=owner,
        visibility=visibility,
        status=status,
        doc_count=doc_count,
        chunk_count=chunk_count,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_kb_orm(
    kb_uuid=VALID_KB_UUID,
    name="测试知识库",
    user_id=1,
    status="active",
    visibility="private",
):
    """详情路由读 kb.user_id 并构建 KnowledgeBaseResponse，需真实 ORM 实例。"""
    return KnowledgeBase(
        id=1,
        uuid=kb_uuid,
        name=name,
        description=None,
        user_id=user_id,
        visibility=visibility,
        status=status,
        doc_count=0,
        chunk_count=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_list_data(total=1, page=1, page_size=20, items=None):
    if items is None:
        items = [_make_kb_response()]
    return KnowledgeBaseListResponse(total=total, page=page, page_size=page_size, items=items)


class TestKBCreateV1:
    """POST /api/v1/knowledge-bases — 创建知识库"""

    URL = "/api/v1/knowledge-bases"

    @pytest.mark.asyncio
    async def test_create_success_201(self, async_client, auth_headers):
        with patch("app.api.knowledge_base_v1.create_kb", new_callable=AsyncMock) as mock:
            mock.return_value = _make_kb_response(name="公司知识库", description="测试描述")

            response = await async_client.post(
                self.URL,
                json={"name": "公司知识库", "description": "测试描述", "visibility": "private"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["code"] == "0"
        assert body["message"] == "知识库创建成功"
        assert_data_matches_schema("KnowledgeBase", body["data"])
        assert body["data"]["name"] == "公司知识库"
        assert body["data"]["visibility"] == "private"

    @pytest.mark.asyncio
    async def test_create_name_conflict_409(self, async_client, auth_headers):
        from app.core.exceptions import KnowledgeBaseNameExistsException

        with patch("app.api.knowledge_base_v1.create_kb", new_callable=AsyncMock) as mock:
            mock.side_effect = KnowledgeBaseNameExistsException("公司知识库")

            response = await async_client.post(
                self.URL, json={"name": "公司知识库"}, headers=auth_headers
            )

        assert response.status_code == 409
        assert response.json()["code"] == "E1002"

    @pytest.mark.asyncio
    async def test_create_no_auth_401(self, async_client):
        response = await async_client.post(self.URL, json={"name": "测试"})
        assert response.status_code == 401


class TestKBListV1:
    """GET /api/v1/knowledge-bases — 统一可见列表"""

    URL = "/api/v1/knowledge-bases"

    @pytest.mark.asyncio
    async def test_list_all_200(self, async_client, auth_headers):
        with patch("app.api.knowledge_base_v1.list_visible_kbs", new_callable=AsyncMock) as mock:
            mock.return_value = _make_list_data(total=1, items=[_make_kb_response()])

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("KnowledgeBaseList", body["data"])
        # scope 查询参数须传递到 service
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.kwargs["scope"] == "all"
        assert call_args.kwargs["q"] is None

    @pytest.mark.asyncio
    async def test_list_scope_public_passed(self, async_client, auth_headers):
        with patch("app.api.knowledge_base_v1.list_visible_kbs", new_callable=AsyncMock) as mock:
            mock.return_value = _make_list_data(total=0, items=[])

            response = await async_client.get(
                f"{self.URL}?scope=public&q=合规", headers=auth_headers
            )

        assert response.status_code == 200
        call_args = mock.await_args
        assert call_args is not None
        assert call_args.kwargs["scope"] == "public"
        assert call_args.kwargs["q"] == "合规"

    @pytest.mark.asyncio
    async def test_list_invalid_scope_422(self, async_client, auth_headers):
        response = await async_client.get(f"{self.URL}?scope=bogus", headers=auth_headers)
        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_list_page_size_over_100_422(self, async_client, auth_headers):
        response = await async_client.get(f"{self.URL}?page_size=101", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_no_auth_401(self, async_client):
        response = await async_client.get(self.URL)
        assert response.status_code == 401


class TestKBGetV1:
    """GET /api/v1/knowledge-bases/{kb_id} — 详情"""

    URL = f"/api/v1/knowledge-bases/{VALID_KB_UUID}"

    @pytest.mark.asyncio
    async def test_get_success_200(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.get_kb", new_callable=AsyncMock) as mock,
            patch(
                "app.api.knowledge_base_v1.resolve_user_uuid", new_callable=AsyncMock
            ) as mock_owner,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_kb_orm()
            mock_owner.return_value = _platform_uuid(1)

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("KnowledgeBase", body["data"])
        assert body["data"]["uuid"] == VALID_KB_UUID
        assert body["data"]["owner"] == _platform_uuid(1)
        assert "id" not in body["data"]

    @pytest.mark.asyncio
    async def test_get_not_found_404(self, async_client, auth_headers):
        with patch(
            "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.side_effect = KnowledgeBaseNotFoundException(VALID_KB_UUID)

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["code"] == "E1001"

    @pytest.mark.asyncio
    async def test_get_permission_denied_403(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.get_kb", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 2
            mock.side_effect = PermissionDeniedException()

            response = await async_client.get(
                f"/api/v1/knowledge-bases/{VALID_KB_UUID_2}", headers=auth_headers
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"


class TestKBUpdateV1:
    """PATCH /api/v1/knowledge-bases/{kb_id} — 更新"""

    URL = f"/api/v1/knowledge-bases/{VALID_KB_UUID}"

    @pytest.mark.asyncio
    async def test_update_name_200(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.update_kb", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_kb_response(name="新名称")

            response = await async_client.patch(
                self.URL, json={"name": "新名称"}, headers=auth_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("KnowledgeBase", body["data"])
        assert body["data"]["name"] == "新名称"

    @pytest.mark.asyncio
    async def test_update_permission_denied_403(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.update_kb", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 2
            mock.side_effect = PermissionDeniedException()

            response = await async_client.patch(
                f"/api/v1/knowledge-bases/{VALID_KB_UUID_2}",
                json={"visibility": "public"},
                headers=auth_headers,
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"

    @pytest.mark.asyncio
    async def test_update_not_found_404(self, async_client, auth_headers):
        with patch(
            "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.side_effect = KnowledgeBaseNotFoundException(VALID_KB_UUID)

            response = await async_client.patch(
                self.URL, json={"name": "新名称"}, headers=auth_headers
            )

        assert response.status_code == 404
        assert response.json()["code"] == "E1001"


class TestKBDeleteV1:
    """DELETE /api/v1/knowledge-bases/{kb_id} — 删除（204 无正文）"""

    URL = f"/api/v1/knowledge-bases/{VALID_KB_UUID}"

    @pytest.mark.asyncio
    async def test_delete_success_204(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.delete_kb", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1

            response = await async_client.delete(self.URL, headers=auth_headers)

        assert response.status_code == 204, response.text
        assert response.text == ""
        mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_permission_denied_403(self, async_client, auth_headers):
        with (
            patch(
                "app.api.knowledge_base_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.knowledge_base_v1.delete_kb", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 2
            mock.side_effect = PermissionDeniedException()

            response = await async_client.delete(
                f"/api/v1/knowledge-bases/{VALID_KB_UUID_2}", headers=auth_headers
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E5005"

    @pytest.mark.asyncio
    async def test_delete_no_auth_401(self, async_client):
        response = await async_client.delete(self.URL)
        assert response.status_code == 401
