"""Chat v1 API 验收测试——canonical SSE、generation 标识与幂等取消。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import StreamingResponse


async def _legacy_stream():
    yield 'event: meta\ndata: {"conversation_id":"conv-1","task_id":"gen-1"}\n\n'
    yield 'event: message\ndata: {"delta":"回答"}\n\n'
    yield 'event: sources\ndata: {"chunks":[]}\n\n'
    yield 'event: finish\ndata: {"message_id":"msg-1","title":null,"token_usage":{}}\n\n'


@pytest.mark.asyncio
async def test_v1_chat_stream输出canonical事件与单调id(async_client, auth_headers):
    """API.md §12：v1 不暴露旧 message/finish 事件名。"""
    with patch("app.api.chat_v1.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = StreamingResponse(
            _legacy_stream(),
            media_type="text/event-stream",
        )
        response = await async_client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": None,
                "knowledge_base_id": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                "question": "测试问题",
                "deep_thinking": False,
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert '"generation_id":"gen-1"' in response.text.replace(" ", "")
    assert "event: message.delta" in response.text
    assert "event: done" in response.text
    assert "event: message\n" not in response.text
    assert "event: finish" not in response.text
    assert response.text.count("id:") == 4
    assert [line for line in response.text.splitlines() if line.startswith("id:")] == [
        "id: 1",
        "id: 2",
        "id: 3",
        "id: 4",
    ]
    assert mock_chat.await_args.kwargs["platform_user_id"] == "550e8400-e29b-41d4-a716-446655440001"


@pytest.mark.asyncio
async def test_v1_generation_cancel调用生命周期服务(async_client, auth_headers):
    """API.md §7：取消命令幂等，并按当前创建者授权。"""
    result = {
        "generation_id": "gen-1",
        "status": "canceled",
        "idempotent_replayed": False,
    }
    with patch(
        "app.api.chat_v1.cancel_generation",
        new_callable=AsyncMock,
        return_value=result,
    ) as mock_cancel:
        response = await async_client.post(
            "/api/v1/chat/generations/gen-1/cancel",
            headers=auth_headers,
        )

    assert response.status_code == 202
    assert response.json() == result
    mock_cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_v1_generation_cancel重复请求返回同一终态(async_client, auth_headers):
    result = {
        "generation_id": "gen-1",
        "status": "canceled",
        "idempotent_replayed": True,
    }
    with patch(
        "app.api.chat_v1.cancel_generation",
        new_callable=AsyncMock,
        return_value=result,
    ):
        response = await async_client.post(
            "/api/v1/chat/generations/gen-1/cancel",
            headers=auth_headers,
        )

    assert response.status_code == 202
    assert response.json()["idempotent_replayed"] is True


@pytest.mark.asyncio
async def test_旧chat入口记录废弃调用量且保持legacy事件(async_client, auth_headers):
    async def legacy_only():
        yield 'event: meta\ndata: {"conversation_id":"conv-1","task_id":"gen-1"}\n\n'
        yield 'event: finish\ndata: {"message_id":"msg-1"}\n\n'

    with (
        patch("app.api.chat.chat", new_callable=AsyncMock) as mock_chat,
        patch("app.api.chat.record_old_chat_call", new_callable=AsyncMock) as record_mock,
    ):
        mock_chat.return_value = StreamingResponse(legacy_only(), media_type="text/event-stream")
        response = await async_client.post(
            "/api/chat",
            json={
                "conversation_id": None,
                "kb_id": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                "question": "测试问题",
                "deep_thinking": False,
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    record_mock.assert_awaited_once_with("stream")
    assert "event: finish" in response.text
    assert "event: done" not in response.text
