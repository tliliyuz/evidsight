"""Chat v1 SSE 逐事件校验 — 对齐 TESTING.md §4/§131 与 API.md §12。

TESTING.md §131：Chat/Research SSE 除路径外还必须逐事件校验事件名、顺序与
每种 data Schema。本文件沿用 canned legacy 流手法（mock chat() 返回 legacy
事件），走真实 `/api/v1/chat/stream` 路由后，用 `assert_sse_events` 对
`x-sse-data-schemas` 映射做逐帧 jsonschema 校验：
- 事件名 ⊆ {meta, message.delta, sources, error, done}（未知事件名即失败）；
- 首帧必须为 meta；
- 终态必须为 done 或 error；
- 每帧 data 与 Chat*EventData / StreamErrorEventData 一致。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import StreamingResponse

from tests.contract.openapi_utils import assert_sse_events, load_sse_event_schemas

STREAM_PATH = "/api/v1/chat/stream"
KB_ID = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"

# canonical wire 投影全 12 键（对齐 project_wire_source / OpenAPI ChatSource）
_WIRE_CHUNK = {
    "chunk_index": 1,
    "doc_name": "测试文档.pdf",
    "score": 0.95,
    "document_uuid": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
    "segment_id": "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
    "page": 1,
    "section_title": None,
    "section_path": None,
    "preview_text": None,
    "preview_range": None,
    "highlight_start": None,
    "highlight_end": None,
}


def _post(client, auth_headers):
    return client.post(
        STREAM_PATH,
        json={
            "conversation_id": None,
            "knowledge_base_id": KB_ID,
            "question": "测试问题",
            "deep_thinking": False,
        },
        headers=auth_headers,
    )


async def _legacy_stream_full():
    """完整 legacy 事件序列：meta → message → sources → finish（终态 done）。"""
    yield 'event: meta\ndata: {"conversation_id":"conv-1","task_id":"gen-1"}\n\n'
    yield 'event: message\ndata: {"delta":"回答"}\n\n'
    yield "event: sources\ndata: " + json.dumps({"chunks": [_WIRE_CHUNK]}) + "\n\n"
    yield (
        'event: finish\ndata: {"message_id":7,"title":null,'
        '"token_usage":{"prompt":10,"completion":5,"total":15}}\n\n'
    )


async def _legacy_stream_error():
    """异常序列：meta → error（终态 error）。"""
    yield 'event: meta\ndata: {"conversation_id":"conv-1","task_id":"gen-1"}\n\n'
    yield 'event: error\ndata: {"code":"CHAT_STREAM_FAILED","message":"生成失败","retryable":false}\n\n'


@pytest.mark.asyncio
async def test_canonical_stream_逐事件校验_首帧meta_终态done(async_client, auth_headers):
    """完整流：事件名⊆允许集、首帧 meta、终态 done，data 逐帧符合 schema。"""
    with patch("app.api.chat_v1.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = StreamingResponse(
            _legacy_stream_full(), media_type="text/event-stream"
        )
        response = await _post(async_client, auth_headers)

    assert response.status_code == 200
    event_schemas = load_sse_event_schemas(STREAM_PATH, "post")
    events = assert_sse_events(
        response.text,
        event_schemas,
        first_event="meta",
        terminal_events=frozenset({"done", "error"}),
    )
    assert [name for name, _ in events] == ["meta", "message.delta", "sources", "done"]
    # canonical 投影事实：task_id→generation_id、message→message.delta、finish→done
    assert events[0][1]["generation_id"] == "gen-1"
    assert events[1][1] == {"delta": "回答"}
    assert events[2][1]["chunks"][0]["doc_name"] == "测试文档.pdf"
    assert events[3][1]["message_id"] == 7
    assert events[3][1]["token_usage"]["total"] == 15


@pytest.mark.asyncio
async def test_canonical_stream_异常流_终态error_逐事件校验(async_client, auth_headers):
    """异常流：首帧 meta、终态 error，error data 符合 StreamErrorEventData。"""
    with patch("app.api.chat_v1.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = StreamingResponse(
            _legacy_stream_error(), media_type="text/event-stream"
        )
        response = await _post(async_client, auth_headers)

    assert response.status_code == 200
    event_schemas = load_sse_event_schemas(STREAM_PATH, "post")
    events = assert_sse_events(
        response.text,
        event_schemas,
        first_event="meta",
        terminal_events=frozenset({"done", "error"}),
    )
    assert [name for name, _ in events] == ["meta", "error"]
    assert events[1][1] == {
        "error_code": "CHAT_STREAM_FAILED",
        "message": "生成失败",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_未知事件名_逐事件校验失败(async_client, auth_headers):
    """legacy 流出现 schema 未定义事件名 → assert_sse_events 报错（RED 门禁）。"""

    async def legacy_with_unknown():
        yield 'event: meta\ndata: {"conversation_id":"conv-1","task_id":"gen-1"}\n\n'
        yield 'event: bogus\ndata: {"x": 1}\n\n'

    with patch("app.api.chat_v1.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = StreamingResponse(
            legacy_with_unknown(), media_type="text/event-stream"
        )
        response = await _post(async_client, auth_headers)

    assert response.status_code == 200
    event_schemas = load_sse_event_schemas(STREAM_PATH, "post")
    with pytest.raises(AssertionError):
        assert_sse_events(response.text, event_schemas)
