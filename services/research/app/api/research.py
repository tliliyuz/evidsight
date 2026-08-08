"""研究任务接口（旧前缀 /api/research）—— 收敛期薄适配器。

对齐 API.md §3（迁移态语义）与 §8.2（端点覆盖迁移态）：
- 目标态前缀为 /api/v1/research（API.md §8 表）；本模块为收敛期旧前缀薄适配器，
  复用 v1 相同的 application service 与共享辅助（app/api/research_common.py）。
- 每个路由入口记录废弃调用量指标 `researchmind_old_api_calls_total`（API.md §15：
  观测窗口归零且 Consumer 回归通过后才能删除旧前缀路由）。
- 语义保持与 v1 等价；POST /retry 与 v1 /resume 为同一 service 的不同别名路径。

路由清单：
- POST   ""                                  — 创建研究任务 + Celery 分发（201）
- GET    ""                                  — 任务历史列表（分页 + 状态筛选）
- GET    /{task_id}                          — 任务状态与进度快照
- DELETE /{task_id}                          — FK CASCADE 级联删除
- POST   /{task_id}/cancel                   — 请求取消（§13.2）
- POST   /{task_id}/retry                    — 断点续跑
- GET    /{task_id}/stream                   — SSE 事件流（实时进度推送）
- GET    /{task_id}/state                    — REST 状态快照（轮询降级）
- GET    /{task_id}/report                   — 完整研究报告
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
from app.metrics.emitters import emit_old_api_call
from app.models.enums import TASK_STATUS_ENUM
from app.models.research_task import ResearchTask
from app.schemas.research import ResearchCreateRequest
from app.services.research_service import (
    cancel_task,
    create_task,
    delete_task,
    get_report,
    get_task_detail,
    get_task_list,
    retry_task,
)
from app.tasks.research_task import execute_research_task as _execute_research_task

logger = logging.getLogger(__name__)

router = APIRouter(tags=["研究任务"])


@router.post("", status_code=201)
async def create_research_task(
    req: ResearchCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建研究任务（需登录）。"""
    emit_old_api_call("create")
    result = await create_task(db, current_user["user_id"], req)
    await db.commit()
    if not result.direct_answer:
        _execute_research_task.delay(str(result.task_id))
        message = "研究任务已创建"
    else:
        message = "直接回答已生成"
    return {"code": "0", "message": message, "data": result.model_dump()}


@router.get("")
async def list_research_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: str | None = Query(None, description="按状态筛选"),
    keyword: str | None = Query(None, description="按主题关键字搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的研究任务历史列表（分页）。"""
    emit_old_api_call("list")
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


@router.get("/{task_id}")
async def get_research_task_detail(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """获取研究任务详情（需登录，仅 owner）。"""
    emit_old_api_call("detail")
    result = await get_task_detail(db, task)
    return _ok(result.model_dump())


@router.delete("/{task_id}")
async def delete_research_task(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """删除研究任务（需登录，仅 owner）。"""
    emit_old_api_call("delete")
    await delete_task(db, task)
    return {"code": "0", "message": "研究任务已删除", "data": None}


@router.post("/{task_id}/cancel")
async def cancel_research_task(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """请求取消研究任务（需登录，仅 owner）。"""
    emit_old_api_call("cancel")
    result = await cancel_task(db, task)
    await publish_cancel_requested(task)
    return {"code": "0", "message": "任务已请求取消", "data": result.model_dump()}


@router.post("/{task_id}/retry", status_code=202)
async def retry_research_task(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """断点续跑（需登录，仅 owner）。"""
    emit_old_api_call("retry")
    result = await retry_task(db, task)
    await db.commit()
    _execute_research_task.delay(str(result.task_id))
    # 返回 status="running"（已分发，worker 将立即拾取并转为 running）
    return {
        "code": "0",
        "message": "断点续跑已启动",
        "data": {**result.model_dump(), "status": "running"},
    }


@router.get("/{task_id}/stream")
async def stream_research_task_events(
    request: Request,
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """SSE 事件流 —— 实时推送 Pipeline 进度。"""
    emit_old_api_call("stream")
    snapshot = await build_task_snapshot(task, db)
    return build_task_events_response(request, task, db, snapshot)


@router.get("/{task_id}/state")
async def get_research_task_state(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """REST 状态快照 —— SSE 的等价物，供客户端轮询降级。"""
    emit_old_api_call("state")
    snapshot = await build_task_snapshot(task, db)
    return _ok(snapshot)


@router.get("/{task_id}/report")
async def get_research_task_report(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """获取完整研究报告（含 Evidence Graph 与 Trace）。"""
    emit_old_api_call("report")
    result = await get_report(db, task)
    return _ok(result.model_dump())
