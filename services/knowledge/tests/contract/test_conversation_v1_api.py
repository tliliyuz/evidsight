"""Conversation v1 API 契约测试 — 对齐 API.md §7 与 docs/openapi/evidsight-v1.yaml。

验证 v1 端点的 method/路径/权限/成功状态码（201/200/204）/信封与错误码，
并断言响应 data 字段与 OpenAPI 组件 Schema 一致。v1 创建请求统一使用
knowledge_base_id（对齐 Chat v1 与 API.md §3.1），映射到 service 的 kb_uuid。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import ConversationAccessDeniedException, ConversationNotFoundException
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)

from tests.contract.openapi_utils import assert_data_matches_schema

VALID_CONV_UUID = "550e8400-e29b-41d4-a716-446655440400"
VALID_CONV_UUID_2 = "550e8400-e29b-41d4-a716-446655440401"
VALID_KB_UUID = "550e8400-e29b-41d4-a716-446655440100"
NOW = datetime.now(timezone.utc)


def _platform_uuid(i: int) -> str:
    return f"550e8400-e29b-41d4-a716-4466554400{i:02d}"


def _make_conv_response(title="新对话", kb_uuid=VALID_KB_UUID, kb_status="active"):
    return ConversationResponse(
        uuid=VALID_CONV_UUID,
        owner_user_id=_platform_uuid(1),
        kb_uuid=kb_uuid,
        kb_status=kb_status,
        kb_name="测试知识库",
        original_kb_uuid=None,
        original_kb_name=None,
        title=title,
        message_count=0,
        created_at=NOW,
        updated_at=NOW,
        last_message_at=None,
    )


def _make_detail_response():
    return ConversationDetailResponse(
        **_make_conv_response().model_dump(),
        messages=[
            {
                "id": 1,
                "role": "user",
                "content": "你好",
                "thinking_content": None,
                "created_at": NOW,
            }
        ],
    )


def _make_list_data(total=1, page=1, page_size=20, items=None):
    if items is None:
        items = [_make_conv_response()]
    return ConversationListResponse(total=total, page=page, page_size=page_size, items=items)


class TestConversationCreateV1:
    """POST /api/v1/conversations — 创建会话"""

    URL = "/api/v1/conversations"

    @pytest.mark.asyncio
    async def test_create_success_201(self, async_client, auth_headers):
        with patch("app.api.conversation_v1.create_conversation", new_callable=AsyncMock) as mock:
            mock.return_value = _make_conv_response()

            response = await async_client.post(
                self.URL,
                json={"knowledge_base_id": VALID_KB_UUID, "title": "产品调研"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("Conversation", body["data"])
        assert body["data"]["title"] == "新对话"
        # v1 请求 knowledge_base_id → service ConversationCreate.kb_uuid 映射
        # args: db, user_id, legacy
        call_args = mock.await_args
        assert call_args is not None
        called_with: ConversationCreate = call_args.args[2]
        assert isinstance(called_with, ConversationCreate)
        assert called_with.kb_uuid == VALID_KB_UUID
        assert called_with.title == "产品调研"

    @pytest.mark.asyncio
    async def test_create_missing_kb_id_422(self, async_client, auth_headers):
        response = await async_client.post(
            self.URL, json={"title": "无知识库"}, headers=auth_headers
        )
        assert response.status_code == 422
        assert response.json()["code"] == "E9003"

    @pytest.mark.asyncio
    async def test_create_no_auth_401(self, async_client):
        response = await async_client.post(
            self.URL, json={"knowledge_base_id": VALID_KB_UUID}, headers={}
        )
        assert response.status_code == 401


class TestConversationListV1:
    """GET /api/v1/conversations — 会话列表"""

    URL = "/api/v1/conversations"

    @pytest.mark.asyncio
    async def test_list_success_200(self, async_client, auth_headers):
        with patch("app.api.conversation_v1.list_conversations", new_callable=AsyncMock) as mock:
            mock.return_value = _make_list_data()

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("ConversationList", body["data"])
        assert body["data"]["total"] == 1
        item = body["data"]["items"][0]
        assert "owner_user_id" in item
        assert "kb_uuid" in item


class TestConversationGetV1:
    """GET /api/v1/conversations/{conversation_id} — 会话详情"""

    URL = f"/api/v1/conversations/{VALID_CONV_UUID}"

    @pytest.mark.asyncio
    async def test_get_success_200(self, async_client, auth_headers):
        with (
            patch(
                "app.api.conversation_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch(
                "app.api.conversation_v1.get_conversation_detail", new_callable=AsyncMock
            ) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_detail_response()

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("ConversationDetail", body["data"])
        assert body["data"]["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_not_found_404(self, async_client, auth_headers):
        with patch(
            "app.api.conversation_v1.resolve_uuid_to_id", new_callable=AsyncMock
        ) as mock_resolve:
            # ConversationNotFoundException 仅接受内部 conv_id（int）
            mock_resolve.side_effect = ConversationNotFoundException(999)

            response = await async_client.get(self.URL, headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["code"] == "E3001"


class TestConversationRenameV1:
    """PATCH /api/v1/conversations/{conversation_id} — 重命名"""

    URL = f"/api/v1/conversations/{VALID_CONV_UUID}"

    @pytest.mark.asyncio
    async def test_rename_success_200(self, async_client, auth_headers):
        with (
            patch(
                "app.api.conversation_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.conversation_v1.rename_conversation", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1
            mock.return_value = _make_conv_response(title="新标题")

            response = await async_client.patch(
                self.URL, json={"title": "新标题"}, headers=auth_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "0"
        assert_data_matches_schema("Conversation", body["data"])
        assert body["data"]["title"] == "新标题"
        # args: db, conv_id, user_id, req
        call_args = mock.await_args
        assert call_args is not None
        assert isinstance(call_args.args[3], ConversationUpdate)

    @pytest.mark.asyncio
    async def test_rename_access_denied_403(self, async_client, auth_headers):
        with (
            patch(
                "app.api.conversation_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.conversation_v1.rename_conversation", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 2
            mock.side_effect = ConversationAccessDeniedException()

            response = await async_client.patch(
                f"/api/v1/conversations/{VALID_CONV_UUID_2}",
                json={"title": "新标题"},
                headers=auth_headers,
            )

        assert response.status_code == 403
        assert response.json()["code"] == "E3002"


class TestConversationDeleteV1:
    """DELETE /api/v1/conversations/{conversation_id} — 删除（204 无正文）"""

    URL = f"/api/v1/conversations/{VALID_CONV_UUID}"

    @pytest.mark.asyncio
    async def test_delete_success_204(self, async_client, auth_headers):
        with (
            patch(
                "app.api.conversation_v1.resolve_uuid_to_id", new_callable=AsyncMock
            ) as mock_resolve,
            patch("app.api.conversation_v1.delete_conversation", new_callable=AsyncMock) as mock,
        ):
            mock_resolve.return_value = 1

            response = await async_client.delete(self.URL, headers=auth_headers)

        assert response.status_code == 204, response.text
        assert response.text == ""
        mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_no_auth_401(self, async_client):
        response = await async_client.delete(self.URL)
        assert response.status_code == 401
