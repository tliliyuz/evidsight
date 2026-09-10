"""Chat generation 生命周期服务验收测试。"""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest


def _db_with_generation(generation):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = generation
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "running"])
async def test_pending或running取消后进入canceled(status):
    from app.services.chat_generation_service import cancel_generation

    generation = SimpleNamespace(uuid="gen-1", status=status, completed_at=None)
    db = _db_with_generation(generation)

    result = await cancel_generation(db, "gen-1", "user-1")

    assert generation.status == "canceled"
    assert generation.completed_at is not None
    assert result == {
        "generation_id": "gen-1",
        "status": "canceled",
        "idempotent_replayed": False,
    }
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_canceled重复取消为幂等重放():
    from app.services.chat_generation_service import cancel_generation

    generation = SimpleNamespace(uuid="gen-1", status="canceled", completed_at=object())
    db = _db_with_generation(generation)

    result = await cancel_generation(db, "gen-1", "user-1")

    assert result["idempotent_replayed"] is True
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_completed或failed取消返回状态冲突(status):
    from app.core.exceptions import ChatGenerationStateConflictException
    from app.services.chat_generation_service import cancel_generation

    generation = SimpleNamespace(uuid="gen-1", status=status, completed_at=object())
    db = _db_with_generation(generation)

    with pytest.raises(ChatGenerationStateConflictException) as exc_info:
        await cancel_generation(db, "gen-1", "user-1")

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "CHAT_GENERATION_STATE_CONFLICT"


@pytest.mark.asyncio
async def test_不存在或非创建者统一返回安全404():
    from app.core.exceptions import ChatGenerationNotFoundException
    from app.services.chat_generation_service import cancel_generation

    db = _db_with_generation(None)

    with pytest.raises(ChatGenerationNotFoundException) as exc_info:
        await cancel_generation(db, "gen-1", "other-user")

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "CHAT_GENERATION_NOT_FOUND"


def test_generation模型与message外键符合数据库规范():
    from app.models.chat_generation import ChatGeneration
    from app.models.message import Message

    columns = ChatGeneration.__table__.c
    assert set(
        [
            "uuid",
            "conversation_id",
            "platform_user_id",
            "kb_uuid",
            "status",
            "started_at",
            "completed_at",
        ]
    ).issubset(columns.keys())
    assert "generation_id" in Message.__table__.c


@pytest.mark.asyncio
async def test_chat服务创建running_generation并把uuid写入meta():
    from app.services import chat_service

    conv = SimpleNamespace(id=9, uuid="conv-1", kb_id=3)
    pipeline_result = SimpleNamespace(
        evidence_review=None,
        prompt_result=SimpleNamespace(),
        reranked_output=SimpleNamespace(),
        doc_map={},
    )
    generation = SimpleNamespace(uuid="gen-persisted-1")
    db = AsyncMock()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            chat_service,
            "_validate_and_prepare",
            AsyncMock(return_value=(conv, False, pipeline_result)),
        )
        create_mock = AsyncMock(return_value=generation)
        monkeypatch.setattr(chat_service, "create_generation", create_mock, raising=False)

        response = await chat_service.chat(
            db=db,
            user_id=1,
            role="user",
            conversation_id=None,
            kb_id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
            question="测试",
            deep_thinking=False,
            platform_user_id="550e8400-e29b-41d4-a716-446655440001",
        )
        first_event = await response.body_iterator.__anext__()
        await response.body_iterator.aclose()

    create_mock.assert_awaited_once()
    assert "task_id" in first_event
    assert "gen-persisted-1" in first_event


@pytest.mark.asyncio
async def test_generation已取消时固定响应不持久化assistant且无成功终态():
    from app.models.conversation import Conversation
    from app.services import sse_stream

    conv = SimpleNamespace(id=9, uuid="conv-1")
    persist_mock = AsyncMock(return_value=(12, None))
    canceled_mock = AsyncMock(return_value=True)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(sse_stream, "_persist_message", persist_mock)
        monkeypatch.setattr(
            sse_stream,
            "is_generation_canceled",
            canceled_mock,
            raising=False,
        )
        events = [
            event
            async for event in sse_stream._generate_meta_response(
                cast(Conversation, conv),
                False,
                "测试",
                generation_uuid="gen-1",
            )
        ]

    persist_mock.assert_not_awaited()
    assert not any("event: finish" in event for event in events)


@pytest.mark.asyncio
async def test_成功终态不会覆盖已取消generation():
    from app.services.chat_generation_service import set_generation_terminal

    generation = SimpleNamespace(
        uuid="gen-1",
        status="canceled",
        completed_at=object(),
        input_tokens=None,
        output_tokens=None,
        error_code=None,
        error_summary=None,
    )
    db = _db_with_generation(generation)

    changed = await set_generation_terminal(
        db,
        "gen-1",
        "completed",
        input_tokens=10,
        output_tokens=20,
    )

    assert changed is False
    assert generation.status == "canceled"
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_SSE断开把仍在运行的generation收敛为canceled():
    from app.services import chat_service

    async def unfinished_stream():
        yield "event: meta\n\ndata: {}\n\n"
        yield "event: message\n\ndata: {}\n\n"

    disconnect_mock = AsyncMock()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            chat_service,
            "cancel_generation_on_disconnect",
            disconnect_mock,
            raising=False,
        )
        stream = chat_service._guard_generation_stream(unfinished_stream(), "gen-1")
        await stream.__anext__()
        await stream.aclose()

    disconnect_mock.assert_awaited_once_with("gen-1")
