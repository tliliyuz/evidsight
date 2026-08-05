"""Research v1 API — /api/v1/research/tasks 幂等创建。

对齐 API.md §8 / §8.1 / §8.2：
- POST /api/v1/research/tasks：202 + Idempotency-Key 必填 + 同 Key 同指纹重放 + 不同指纹 409 E2009；
- 信封沿用全平台既有 {"code","message","data"}（§8.2 迁移态记录，目标态为 API.md §4）。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedException
from app.dependencies import get_current_user, get_db
from app.schemas.research import ResearchCreateRequest
from app.services.research_service import (
    compute_request_fingerprint,
    create_task_idempotent,
)
from app.tasks.research_task import execute_research_task as _execute_research_task

router = APIRouter(tags=["研究任务 v1"])

_IDEMPOTENCY_KEY_MAX_LEN = 128


@router.post("/tasks", status_code=202)
async def create_research_task_v1(
    req: ResearchCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建研究任务（幂等，需登录）。

    对齐 API.md §8.1：
    1. Idempotency-Key 必填（≤ 128 字符），按请求载荷计算指纹；
    2. 同用户同 Key 同指纹 → 返回首次创建的任务（idempotent_replayed=true）；
       不同指纹 → 409 E2009，不创建新任务；
    3. 首次创建后显式 commit 再 Celery 分发（CLAUDE.md 强制规则）。
    """
    idempotency_key = request.headers.get("Idempotency-Key", "")
    if not idempotency_key:
        raise ValidationFailedException("创建研究任务必须携带 Idempotency-Key")
    if len(idempotency_key) > _IDEMPOTENCY_KEY_MAX_LEN:
        raise ValidationFailedException(f"Idempotency-Key 长度不能超过 {_IDEMPOTENCY_KEY_MAX_LEN}")

    request_fingerprint = compute_request_fingerprint(req)
    result = await create_task_idempotent(
        db,
        current_user["user_id"],
        req,
        idempotency_key,
        request_fingerprint,
    )
    await db.commit()

    # 重放命中不重复分发；直接回答跳过 Pipeline
    if not result.direct_answer and not result.idempotent_replayed:
        _execute_research_task.delay(str(result.task_id))
        message = "研究任务已创建"
    elif result.direct_answer:
        message = "直接回答已生成"
    else:
        message = "研究任务已存在（幂等重放）"
    return {"code": "0", "message": message, "data": result.model_dump()}
