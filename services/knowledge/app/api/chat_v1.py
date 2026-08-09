"""Chat v1 API——canonical SSE 与 generation 取消。"""

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.services.chat_generation_service import cancel_generation
from app.services.chat_service import chat

router = APIRouter(prefix="/api/v1/chat", tags=["问答 v1"])


class ChatV1Request(BaseModel):
    conversation_id: str | None = None
    knowledge_base_id: str
    question: str = Field(..., min_length=1, max_length=2000)
    deep_thinking: bool = False


async def _canonical_stream(response: StreamingResponse) -> AsyncIterator[str]:
    sequence = 0
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        if text.startswith(":"):
            yield text
            continue
        event_name: str | None = None
        data = None
        for line in text.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_name == "thinking":
            continue
        if event_name is None or data is None:
            continue
        event_name = {"message": "message.delta", "finish": "done"}.get(event_name, event_name)
        if event_name == "meta" and "task_id" in data:
            data["generation_id"] = data.pop("task_id")
        elif event_name == "sources":
            data = {
                **{key: value for key, value in data.items() if key != "chunks"},
                "chunks": [
                    {
                        key: chunk.get(key)
                        for key in (
                            "chunk_index",
                            "document_uuid",
                            "segment_id",
                            "doc_name",
                            "score",
                            "page",
                            "section_title",
                            "section_path",
                            "preview_text",
                            "preview_range",
                            "highlight_start",
                            "highlight_end",
                        )
                    }
                    for chunk in data.get("chunks", [])
                ],
            }
        elif event_name == "error":
            data = {
                "error_code": data.get("error_code") or data.get("code") or "CHAT_STREAM_FAILED",
                "message": data.get("message", "问答生成失败"),
                "retryable": bool(data.get("retryable", False)),
            }
        sequence += 1
        yield (
            f"id: {sequence}\n"
            f"event: {event_name}\n"
            f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
        )


@router.post("/stream")
async def stream_chat_v1(
    req: ChatV1Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    legacy_response = await chat(
        db=db,
        user_id=current_user["user_id"],
        role=current_user["role"],
        conversation_id=req.conversation_id,
        kb_id=req.knowledge_base_id,
        question=req.question,
        deep_thinking=req.deep_thinking,
        platform_user_id=current_user["platform_user_id"],
    )
    return StreamingResponse(
        _canonical_stream(legacy_response),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/generations/{generation_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_chat_generation_v1(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await cancel_generation(db, generation_id, current_user["platform_user_id"])
