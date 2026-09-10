"""Chat generation 生命周期服务。"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.exceptions import (
    ChatGenerationNotFoundException,
    ChatGenerationStateConflictException,
)
from app.models.chat_generation import ChatGeneration


async def create_generation(
    db: AsyncSession,
    conversation_id: int,
    platform_user_id: str,
    kb_uuid: str,
) -> ChatGeneration:
    """创建并提交 running generation，使 meta 发出前已有可取消事实。"""
    now = datetime.now(timezone.utc)
    generation = ChatGeneration(
        conversation_id=conversation_id,
        platform_user_id=platform_user_id,
        kb_uuid=kb_uuid,
        status="running",
        started_at=now,
    )
    db.add(generation)
    await db.flush()
    await db.commit()
    await db.refresh(generation)
    return generation


async def cancel_generation(
    db: AsyncSession,
    generation_id: str,
    platform_user_id: str,
) -> dict:
    """按创建者锁定 generation 并执行幂等取消。"""
    result = await db.execute(
        select(ChatGeneration)
        .where(
            ChatGeneration.uuid == generation_id,
            ChatGeneration.platform_user_id == platform_user_id,
        )
        .with_for_update()
    )
    generation = result.scalar_one_or_none()
    if generation is None:
        raise ChatGenerationNotFoundException()

    if generation.status == "canceled":
        return {
            "generation_id": generation.uuid,
            "status": "canceled",
            "idempotent_replayed": True,
        }
    if generation.status in {"completed", "failed"}:
        raise ChatGenerationStateConflictException(generation.status)

    generation.status = "canceled"
    generation.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "generation_id": generation.uuid,
        "status": "canceled",
        "idempotent_replayed": False,
    }


async def set_generation_terminal(
    db: AsyncSession,
    generation_id: str,
    status: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> bool:
    """只允许 active generation 进入终态，绝不覆盖并发取消。"""
    result = await db.execute(
        select(ChatGeneration).where(ChatGeneration.uuid == generation_id).with_for_update()
    )
    generation = result.scalar_one_or_none()
    if generation is None or generation.status not in {"pending", "running"}:
        return False
    generation.status = status
    generation.completed_at = datetime.now(timezone.utc)
    generation.input_tokens = input_tokens
    generation.output_tokens = output_tokens
    generation.error_code = error_code
    generation.error_summary = error_summary
    await db.flush()
    return True


async def is_generation_canceled(generation_id: str) -> bool:
    async with async_session() as db:
        result = await db.execute(
            select(ChatGeneration.status).where(ChatGeneration.uuid == generation_id)
        )
        return result.scalar_one_or_none() == "canceled"


async def fail_generation(generation_id: str, code: str, summary: str) -> None:
    async with async_session() as db:
        await set_generation_terminal(
            db,
            generation_id,
            "failed",
            error_code=code,
            error_summary=summary[:500],
        )
        await db.commit()


async def cancel_generation_on_disconnect(generation_id: str) -> None:
    """连接关闭时仅收敛仍活跃的 generation，不覆盖既有终态。"""
    async with async_session() as db:
        await set_generation_terminal(db, generation_id, "canceled")
        await db.commit()
