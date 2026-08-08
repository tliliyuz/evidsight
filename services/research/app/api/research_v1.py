"""Research v1 API — /api/v1/research/tasks 全量研究命令与查询。

对齐 API.md §8（Research Task API，目标态前缀）：
- POST   /api/v1/research/tasks：202 + Idempotency-Key 必填 + 同 Key 同指纹重放 + 不同指纹 409 E2009；
- GET    /api/v1/research/tasks：任务历史列表（分页 + 状态筛选）；
- GET    /api/v1/research/tasks/{task_id}：任务状态与进度快照；
- POST   /api/v1/research/tasks/{task_id}/cancel：请求取消（§13.2）；
- POST   /api/v1/research/tasks/{task_id}/resume：断点续跑（旧前缀 /retry 语义等价）；
- DELETE /api/v1/research/tasks/{task_id}：FK CASCADE 级联删除（204）；
- GET    /api/v1/research/tasks/{task_id}/events：SSE 事件流（§13/§15）；
- GET    /api/v1/research/tasks/{task_id}/state：REST 状态快照（轮询降级）；
- GET    /api/v1/research/tasks/{task_id}/report：完整研究报告（含 Evidence Graph 与 Trace）。

切片 8 收敛：全部研究命令与查询收敛到 /api/v1/research/*（对齐 ROADMAP
2026-08-05「Research API 路径迁移到 /api/v1/research」裁决）；旧前缀
/api/research 收敛期间保持可用（API.md §8.2）。

信封沿用全平台既有 {"code","message","data"}（API.md §8.2 迁移态）。
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.research_common import (
    _ok,
    build_task_events_response,
    build_task_snapshot,
    publish_cancel_requested,
)
from app.core.exceptions import ValidationFailedException
from app.dependencies import get_current_user, get_db, require_task_accessible
from app.models.enums import TASK_STATUS_ENUM
from app.models.research_task import ResearchTask
from app.schemas.research import ResearchCreateRequest
from app.services.research_service import (
    cancel_task,
    compute_request_fingerprint,
    create_task_idempotent,
    delete_task,
    get_report,
    get_task_detail,
    get_task_list,
    retry_task,
)
from app.tasks.research_task import execute_research_task as _execute_research_task

logger = logging.getLogger(__name__)

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


@router.get("/tasks")
async def list_research_tasks_v1(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: str | None = Query(None, description="按状态筛选"),
    keyword: str | None = Query(None, description="按主题关键字搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的研究任务历史列表（分页）。

    对齐 API.md §8 GET /api/v1/research/tasks。
    按 created_at DESC 排序，支持 status 筛选与 topic 关键字模糊搜索。
    """
    if status is not None and status not in TASK_STATUS_ENUM:
        raise ValidationFailedException(f"status 参数非法，可选值: {', '.join(TASK_STATUS_ENUM)}")

    result = await get_task_list(
        db,
        user_id=current_user["user_id"],
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
    )
    return _ok(result.model_dump())


@router.get("/tasks/{task_id}")
async def get_research_task_detail_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """获取研究任务详情（需登录，仅 owner）。

    对齐 API.md §8 GET /api/v1/research/tasks/{task_id}。
    含 status / current_phase / progress 进度快照。
    """
    result = await get_task_detail(db, task)
    return _ok(result.model_dump())


@router.post("/tasks/{task_id}/cancel", status_code=202)
async def cancel_research_task_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """请求取消研究任务（需登录，仅 owner）。

    对齐 RESEARCH_PIPELINE §13.2：取消是请求而非终态 —— API 只持久化
    cancel_requested_at；Worker 在安全检查点停止后由 TaskStateResolver
    推导 canceled / partially_completed 等终态。此处发布取消请求事件，
    终态事件由 Worker/Resolver 在安全停止后发布。
    """
    result = await cancel_task(db, task)
    await publish_cancel_requested(task)
    return {"code": "0", "message": "任务已请求取消", "data": result.model_dump()}


@router.post("/tasks/{task_id}/resume", status_code=202)
async def resume_research_task_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """断点续跑（需登录，仅 owner）。

    对齐 API.md §8 POST /api/v1/research/tasks/{task_id}/resume（旧前缀 /retry
    语义等价）。从最后 checkpoint 恢复执行，已完成 Step 复用，Evidence 只追加不覆盖。
    """
    result = await retry_task(db, task)
    await db.commit()
    _execute_research_task.delay(str(result.task_id))
    # 返回 status="running"（已分发，worker 将立即拾取并转为 running）
    return {
        "code": "0",
        "message": "断点续跑已启动",
        "data": {**result.model_dump(), "status": "running"},
    }


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_research_task_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """删除研究任务（需登录，仅 owner）。

    对齐 API.md §8 DELETE /api/v1/research/tasks/{task_id}（204）。
    FK ON DELETE CASCADE 自动清理全部派生数据（Steps / Sources / Evidence / Report Sections）。
    """
    await delete_task(db, task)
    return None


@router.get("/tasks/{task_id}/events")
async def stream_research_task_events_v1(
    request: Request,
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """SSE 事件流 —— 实时推送 Pipeline 进度。

    对齐 API.md §13 / RESEARCH_PIPELINE §15。
    Content-Type: text/event-stream，15s 心跳。
    """
    snapshot = await build_task_snapshot(task, db)
    return build_task_events_response(request, task, db, snapshot)


@router.get("/tasks/{task_id}/state")
async def get_research_task_state_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """REST 状态快照 —— SSE 的等价物，供客户端轮询降级。

    对齐 API.md §8（旧前缀 /state 语义等价）。
    """
    snapshot = await build_task_snapshot(task, db)
    return _ok(snapshot)


@router.get("/tasks/{task_id}/report")
async def get_research_task_report_v1(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """获取完整研究报告（含 Evidence Graph 与 Trace）。

    对齐 API.md §8（旧前缀 /report 语义等价，§8.2 收敛目标）。仅 completed /
    partially_completed 任务可获取。
    """
    result = await get_report(db, task)
    return _ok(result.model_dump())
