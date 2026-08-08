"""研究任务业务逻辑 — 创建 / 列表 / 详情 / 删除 / 报告获取

对齐 API.md §3.1 / §3.3：
- create_task()：校验 → 写入 research_tasks + 首个 research_step → commit → Celery 分发
- get_task_list()：当前用户任务分页列表，按 created_at DESC
- get_task_detail()：单任务状态 + progress 快照
- delete_task()：FK CASCADE 级联清理全部派生数据
- get_report()：获取完整研究报告（含 Evidence Graph 与 Trace）
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    IdempotencyKeyConflictException,
    InvalidDepthException,
    InvalidRequirementsException,
    InvalidTaskTypeException,
    TaskStatusConflictException,
)
from app.core.identity_status_client import check_user_status
from app.metrics import emit_task_status_transition
from app.models.evidence_item import EvidenceItem
from app.models.report import Report
from app.models.report_revision import ReportRevision
from app.models.report_section import ReportSection
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.models.research_task_knowledge_base import ResearchTaskKnowledgeBase
from app.models.section_evidence import SectionEvidence
from app.schemas.research import (
    VALID_DEPTHS,
    VALID_TASK_TYPES,
    ProgressSchema,
    ReportSchema,
    ReportSectionSchema,
    ReportSectionSourceSchema,
    ReportSourceSchema,
    ResearchCancelResponse,
    ResearchCreateRequest,
    ResearchCreateResponse,
    ResearchReportResponse,
    ResearchRetryResponse,
    ResearchTaskListItem,
    ResearchTaskListResponse,
    ResearchTaskResponse,
    ResumeFromSchema,
)
from app.services.budget_service import freeze_budget
from app.services.intent_classifier import (
    INTENT_DIRECT_ANSWER,
    classify_intent,
)
from app.services.pipeline_orchestrator import PHASE_ORDER

logger = logging.getLogger(__name__)


# ── 创建任务 ────────────────────────────────────────────────────


async def create_task(
    db: AsyncSession,
    user_id: str,
    request: ResearchCreateRequest,
    *,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
) -> ResearchCreateResponse:
    """创建研究任务 + 首个 Planning Step（或直接回答）。

    0. 身份状态实时复核：创建任务前调用 Knowledge Identity Status Provider，
       用户禁用/不存在或身份库不可用时失败关闭，不写入任务行、不分发 Worker。
    1. 意图识别：非研究输入直接生成 completed 任务与单章节报告
    2. 研究输入：写入 research_tasks (status=pending) + 首个 planning step

    注意：Celery 分发（commit + delay）由 API 层在返回前执行，
    避免在 Service 层 commit 破坏测试事务隔离。
    """
    await check_user_status(user_id)

    _validate_create_request(request)

    # 来源策略分流：knowledge/hybrid 显式依赖内部知识，直接进入研究 Pipeline；
    # 仅 web 策略保留意图识别（可直接回答非研究主题）。
    if request.source_strategy != "web":
        return await _create_research_task(
            db,
            user_id,
            request,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )

    intent_result = await classify_intent(request.topic)
    if intent_result.intent == INTENT_DIRECT_ANSWER:
        return await _create_direct_answer_task(
            db,
            user_id,
            request,
            intent_result.direct_answer,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )

    return await _create_research_task(
        db,
        user_id,
        request,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )


def compute_request_fingerprint(request: ResearchCreateRequest) -> str:
    """计算创建请求的规范化载荷指纹（API.md §8.1，SHA-256 64 位 hex）。

    覆盖 topic / requirements / source_strategy / knowledge_base_ids；
    同语义载荷（含 Pydantic 默认补全）产生同一指纹。
    """
    canonical = json.dumps(
        {
            "topic": request.topic.strip(),
            "requirements": request.requirements.model_dump(),
            "source_strategy": request.source_strategy,
            "knowledge_base_ids": request.knowledge_base_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def create_task_idempotent(
    db: AsyncSession,
    user_id: str,
    request: ResearchCreateRequest,
    idempotency_key: str,
    request_fingerprint: str,
) -> ResearchCreateResponse:
    """幂等创建（API.md §8.1）：同用户同 Key 同指纹重放，不同指纹 409。

    - 已存在 (user_id, idempotency_key)：指纹一致返回原任务（replayed=true），不一致抛 E2009；
    - 不存在：走 create_task 写入幂等列；并发竞争同一幂等唯一约束时按重放收敛，
      其他 IntegrityError（如 selection_order 唯一冲突）上抛，不得误报 E2009。
    """
    existing = await _find_task_by_idempotency_key(db, user_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyConflictException("相同 Idempotency-Key 的请求载荷与首次创建不一致")
        return _build_replay_response(existing)

    try:
        return await create_task(
            db,
            user_id,
            request,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
    except IntegrityError as exc:
        # 只对「幂等键唯一约束」冲突做并发收敛；其余完整性冲突（KB 选择行
        # selection_order、其他唯一键）保持上抛，避免错误报告 E2009。
        if not _is_idempotency_unique_conflict(exc):
            raise
        # 并发竞争：另一请求已创建同一 (user_id, idempotency_key)，按重放收敛
        await db.rollback()
        existing = await _find_task_by_idempotency_key(db, user_id, idempotency_key)
        if existing is not None and existing.request_fingerprint == request_fingerprint:
            return _build_replay_response(existing)
        raise IdempotencyKeyConflictException(
            "相同 Idempotency-Key 的并发请求载荷不一致，拒绝创建新任务"
        )


def _is_idempotency_unique_conflict(exc: IntegrityError) -> bool:
    """判断 IntegrityError 是否来自幂等键唯一约束
    `uq_research_tasks_user_idempotency(user_id, idempotency_key)`。

    MySQL 报错携带约束名；SQLite 报错携带冲突列名，两种都识别。
    """
    message = str(exc)
    return "uq_research_tasks_user_idempotency" in message or "idempotency_key" in message


async def _find_task_by_idempotency_key(
    db: AsyncSession, user_id: str, idempotency_key: str
) -> ResearchTask | None:
    """按 (user_id, idempotency_key) 查找既有任务（DATABASE.md §5.1 唯一约束）。"""
    stmt = select(ResearchTask).where(
        ResearchTask.user_id == user_id,
        ResearchTask.idempotency_key == idempotency_key,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _build_replay_response(task: ResearchTask) -> ResearchCreateResponse:
    """幂等重放响应：返回该任务当前状态（API.md §8.1），不反映创建时刻。"""
    is_direct_answer = (task.requirements or {}).get("task_type") == "direct_answer"
    return ResearchCreateResponse(
        task_id=task.id,
        status=task.status,
        created_at=task.created_at,
        direct_answer=is_direct_answer,
        idempotent_replayed=True,
    )


async def _create_research_task(
    db: AsyncSession,
    user_id: str,
    request: ResearchCreateRequest,
    *,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
) -> ResearchCreateResponse:
    """研究意图：创建 pending 任务 + planning step。"""
    now = datetime.now(timezone.utc)

    # 1. 创建研究任务
    task = ResearchTask(
        user_id=user_id,
        topic=request.topic.strip(),
        requirements=request.requirements.model_dump(),
        source_strategy=request.source_strategy,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        status="pending",
        current_phase=None,
        created_at=now,
        started_at=now,  # 记录派发时间，供 pending 超时监察使用
    )
    db.add(task)
    await db.flush()  # 获取 task.id

    # 预算冻结（RESEARCH_PIPELINE §14）：创建时服务端默认推导冻结上限并初始化结算用量
    freeze_budget(
        task,
        request.requirements.model_dump(),
        request.source_strategy,
    )
    await db.flush()

    # 1.1 持久化知识库选择（selection_order 保留用户选择顺序，供 pipeline 检索顺序使用）
    for order, kb_id in enumerate(request.knowledge_base_ids):
        db.add(
            ResearchTaskKnowledgeBase(
                task_id=task.id,
                knowledge_base_id=kb_id,
                selection_order=order,
            )
        )

    # 2. 创建首个 Planning Step（pending 状态，等待 Celery Worker 拾取）
    planning_step = ResearchStep(
        task_id=task.id,
        step_type="planning",
        status="pending",
        label="Planning：拆解研究主题",
    )
    db.add(planning_step)

    # 3. 初始化全局进度分母为七阶段（与 PHASE_ORDER 一致）
    # 分子 completed_steps 同样按 Phase 维度计数，每完成一个 Phase +1。
    # 分母固定为 7，杜绝动态扩展导致的百分比错配（如 6/27=22%）。
    task.total_steps = len(PHASE_ORDER)

    # 4. flush 获取 ID（Celery 分发由 API 层在 commit 后执行，
    #    以避免 Service 层 commit 破坏测试事务隔离）
    await db.flush()

    logger.info(
        "研究任务已创建: task_id=%s, user_id=%s, topic=%s, task_type=%s",
        task.id,
        user_id,
        request.topic[:50],
        request.requirements.task_type,
    )

    emit_task_status_transition("pending")

    return ResearchCreateResponse(
        task_id=task.id,
        status="pending",
        created_at=task.created_at,
        direct_answer=False,
    )


async def _create_direct_answer_task(
    db: AsyncSession,
    user_id: str,
    request: ResearchCreateRequest,
    answer_text: str,
    *,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
) -> ResearchCreateResponse:
    """非研究意图：创建已完成任务、单章节报告与空 Evidence Graph Step。

    直接回答任务复用现有报告接口，可进入历史列表并支持审计。
    """
    now = datetime.now(timezone.utc)
    requirements = request.requirements.model_dump()
    requirements["task_type"] = "direct_answer"
    language = requirements.get("language", "zh")

    task = ResearchTask(
        user_id=user_id,
        topic=request.topic.strip(),
        requirements=requirements,
        source_strategy="web",  # 直接回答仅来自模型，不涉及内部知识库
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        status="completed",
        current_phase=None,
        created_at=now,
        started_at=now,
        completed_at=now,
        total_steps=0,
        completed_steps=0,
    )
    db.add(task)
    await db.flush()

    # 单章节报告（切片 4 目标态单写：reports → revision → sections）
    heading = "回答" if language.startswith("zh") else "Answer"
    report = Report(task_id=task.id)
    db.add(report)
    await db.flush()
    revision = ReportRevision(
        report_id=report.id,
        revision_number=1,
        status="published",
        title=request.topic.strip(),
        language=language,
        published_at=now,
    )
    db.add(revision)
    await db.flush()
    report.current_revision_id = revision.id
    section = ReportSection(
        task_id=task.id,
        revision_id=revision.id,
        heading=heading,
        content=answer_text,
        sort_order=0,
    )
    db.add(section)

    # 空 Evidence Graph Step，使 get_report() 可直接读取
    eg_step = ResearchStep(
        task_id=task.id,
        step_type="evidence_graph",
        status="completed",
        label="直接回答",
        input={"topic": request.topic.strip()},
        output={
            "graph": {
                "items": [],
                "sources": [],
                "generated_at": now.isoformat(),
            }
        },
        started_at=now,
        completed_at=now,
        duration_ms=0,
    )
    db.add(eg_step)
    await db.flush()

    logger.info(
        "直接回答任务已创建: task_id=%s, user_id=%s, topic=%s",
        task.id,
        user_id,
        request.topic[:50],
    )

    emit_task_status_transition("completed")

    # 直接构造报告响应，避免创建过程中 ORM 对象过期列触发隐式懒加载
    report = ReportSchema(
        title=task.topic,
        generated_at=now,
        sections=[
            ReportSectionSchema(
                heading=heading,
                content=answer_text,
                sources=[],
            )
        ],
        sources=[],
    )
    return ResearchCreateResponse(
        task_id=task.id,
        status="completed",
        created_at=task.created_at,
        direct_answer=True,
        report=report,
    )


def _validate_create_request(request: ResearchCreateRequest) -> None:
    """校验创建请求的合法性。

    Pydantic 已做基础校验（topic ≤ 500 字符、task_type 枚举约束、
    max_sources 范围等），此处做补充业务校验。
    """
    if len(request.topic.strip()) == 0:
        raise InvalidRequirementsException("topic 不能为空")

    req = request.requirements
    if req.task_type not in VALID_TASK_TYPES:
        raise InvalidTaskTypeException()
    if req.depth not in VALID_DEPTHS:
        raise InvalidDepthException()
    if req.max_sources < 1 or req.max_sources > 50:
        raise InvalidRequirementsException("max_sources 必须在 1-50 之间")


# ── 任务列表 ────────────────────────────────────────────────────


async def get_task_list(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    keyword: str | None = None,
) -> ResearchTaskListResponse:
    """获取当前用户的研究任务历史列表。

    按 created_at DESC 排序，支持 status 筛选、topic 关键字模糊搜索与分页。
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

    # 构建基础查询
    conditions = [ResearchTask.user_id == user_id]
    if status:
        conditions.append(ResearchTask.status == status)
    if keyword and keyword.strip():
        conditions.append(ResearchTask.topic.ilike(f"%{keyword.strip()}%"))

    # 总数查询
    count_q = select(func.count()).select_from(ResearchTask).where(*conditions)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    q = (
        select(ResearchTask)
        .where(*conditions)
        .order_by(ResearchTask.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(q)
    tasks = result.scalars().all()

    # 构建列表项
    items = [_build_list_item(t) for t in tasks]

    return ResearchTaskListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


def _build_list_item(task: ResearchTask) -> ResearchTaskListItem:
    """从 ORM 对象构建列表项响应。

    从 requirements JSON 中提取 task_type 字段。
    """
    requirements = task.requirements or {}
    task_type = requirements.get("task_type", "unknown")

    return ResearchTaskListItem(
        task_id=task.id,
        topic=task.topic,
        status=task.status,
        task_type=task_type,
        total_sources=task.total_sources or 0,
        total_evidence=task.total_evidence or 0,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


# ── 任务详情 ────────────────────────────────────────────────────


async def get_task_detail(
    db: AsyncSession,
    task: ResearchTask,
) -> ResearchTaskResponse:
    """获取研究任务详情（含进度快照）。

    调用方需先通过 require_task_accessible 校验权限并获取 task 对象。
    """
    progress = _build_progress(task)
    return ResearchTaskResponse(
        task_id=task.id,
        topic=task.topic,
        status=task.status,
        current_phase=task.current_phase,
        requirements=task.requirements or {},
        progress=progress,
        total_sources=task.total_sources or 0,
        total_evidence=task.total_evidence or 0,
        error_code=task.error_code,
        error_message=task.error_message,
        recoverable=task.recoverable,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


async def get_report(
    db: AsyncSession,
    task: ResearchTask,
) -> ResearchReportResponse:
    """获取完整研究报告（含 Evidence Graph 与 Trace）。

    调用方需先通过 require_task_accessible 校验权限并获取 task 对象。
    对齐 API.md §3.3 GET /api/research/{task_id}/report。
    """
    if task.status not in {"completed", "partially_completed"}:
        raise TaskStatusConflictException(detail="任务尚未完成，无法获取报告")

    # 读取最新完成的 Evidence Graph Step 的 output["graph"]
    stmt = (
        select(ResearchStep)
        .where(
            ResearchStep.task_id == task.id,
            ResearchStep.step_type == "evidence_graph",
            ResearchStep.status == "completed",
        )
        .order_by(ResearchStep.completed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    eg_step: ResearchStep | None = result.scalar_one_or_none()

    if eg_step is None or not isinstance(eg_step.output, dict):
        raise TaskStatusConflictException(detail="报告尚未生成")

    evidence_graph = eg_step.output.get("graph") or {}

    # 构建 evidence_item.id -> evidence_index 映射
    items = evidence_graph.get("items") or []
    evidence_id_to_index: dict[int, int] = {}
    for item in items:
        if isinstance(item, dict) and "evidence_item_id" in item and "index" in item:
            evidence_id_to_index[item["evidence_item_id"]] = item["index"]

    # 切片 4 单写同源：经 reports → current_revision_id → revision sections 读取（RESEARCH_PIPELINE §11）
    report = (
        await db.execute(select(Report).where(Report.task_id == task.id))
    ).scalar_one_or_none()
    if report is None or not report.current_revision_id:
        raise TaskStatusConflictException(detail="报告尚未生成")
    revision = await db.get(ReportRevision, report.current_revision_id)
    if revision is None or revision.status != "published":
        raise TaskStatusConflictException(detail="报告尚未生成")

    # 组装章节（显式查询，避免 lazy load）
    stmt = (
        select(ReportSection)
        .where(ReportSection.revision_id == revision.id)
        .order_by(ReportSection.sort_order)
    )
    result = await db.execute(stmt)
    sorted_sections = list(result.scalars().all())

    section_ids = [s.id for s in sorted_sections]
    section_evidence_map: dict[int, list[int]] = {sid: [] for sid in section_ids}
    if section_ids:
        stmt = select(SectionEvidence.section_id, SectionEvidence.evidence_id).where(
            SectionEvidence.section_id.in_(section_ids)
        )
        result = await db.execute(stmt)
        for section_id, evidence_id in result.all():
            section_evidence_map.setdefault(section_id, []).append(evidence_id)

    # 预加载 evidence_items.source_id（用于生成 sources.id）
    evidence_ids = []
    for ids in section_evidence_map.values():
        evidence_ids.extend(ids)
    evidence_source_ids: dict[int, int] = {}
    if evidence_ids:
        stmt = select(EvidenceItem.id, EvidenceItem.source_id).where(
            EvidenceItem.id.in_(evidence_ids)
        )
        result = await db.execute(stmt)
        for eid, source_id in result.all():
            evidence_source_ids[eid] = source_id

    report_sections: list[ReportSectionSchema] = []
    for section in sorted_sections:
        section_sources: list[ReportSectionSourceSchema] = []
        seen_indices: set[int] = set()
        for evidence_id in section_evidence_map.get(section.id, []):
            idx = evidence_id_to_index.get(evidence_id)
            if idx is None or idx in seen_indices:
                continue
            seen_indices.add(idx)
            section_sources.append(
                ReportSectionSourceSchema(
                    id=evidence_source_ids.get(evidence_id, 0),
                    evidence_index=idx,
                )
            )
        section_sources.sort(key=lambda x: x.evidence_index)
        report_sections.append(
            ReportSectionSchema(
                heading=section.heading,
                content=section.content,
                sources=section_sources,
            )
        )

    # 组装报告来源
    report_sources: list[ReportSourceSchema] = []
    for src in evidence_graph.get("sources") or []:
        if not isinstance(src, dict):
            continue
        report_sources.append(
            ReportSourceSchema(
                id=src.get("id") or 0,
                url=src.get("url") or "",
                title=src.get("title") or "",
                domain=src.get("domain") or "",
            )
        )

    # 报告生成时间
    generated_at = eg_step.completed_at
    graph_generated_at = evidence_graph.get("generated_at")
    if graph_generated_at:
        try:
            generated_at = datetime.fromisoformat(graph_generated_at)
        except (ValueError, TypeError):
            pass
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    report = ReportSchema(
        title=task.topic,
        generated_at=generated_at,
        sections=report_sections,
        sources=report_sources,
    )

    return ResearchReportResponse(
        task_id=task.id,
        status=task.status,
        report=report,
        evidence_graph=evidence_graph,
        trace=task.trace,
    )


def _build_progress(task: ResearchTask) -> ProgressSchema:
    """从 execution_context 或统计字段构建进度快照。

    API 响应中的 progress 是顶层便利字段，数据来源为
    execution_context.progress，fallback 到 total_steps / completed_steps。
    """
    ec = task.execution_context
    if ec and isinstance(ec, dict):
        pg = ec.get("progress")
        if pg and isinstance(pg, dict):
            progress = float(pg.get("progress", 0.0))
            return ProgressSchema(
                completed_steps=pg.get("completed_steps", task.completed_steps or 0),
                total_steps=pg.get("total_steps", task.total_steps or 0),
                progress=min(max(progress, 0.0), 1.0),
            )

    # fallback：从统计列计算
    total = task.total_steps or 0
    completed = task.completed_steps or 0
    progress = (completed / total) if total > 0 else 0.0
    progress = min(progress, 1.0)
    return ProgressSchema(
        completed_steps=completed,
        total_steps=total,
        progress=round(progress, 2),
    )


# ── 取消任务 ────────────────────────────────────────────────────


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "partially_completed", "canceled"}
)


async def cancel_task(
    db: AsyncSession,
    task: ResearchTask,
) -> ResearchCancelResponse:
    """请求取消研究任务（仅持久化取消请求，不直接改写终态）。

    对齐 RESEARCH_PIPELINE §13.2 / DATABASE.md §8 / ADR-008：
    - 终态校验：completed / failed / partially_completed / canceled 抛 E2003
    - 只写 cancel_requested_at（CAS：仅当 status 为 pending / running 且尚未请求取消）
    - CAS 失败意味着并发状态变更，同样抛 E2003
    - 取消与完成竞态以报告发布事务开始前的条件检查为界：Worker 在安全检查点
      停止后由 TaskStateResolver 推导 canceled / partially_completed 等终态

    注意：本函数不提交事务，由 API 层依赖注入的 get_db 统一提交。
    """
    if task.status in TERMINAL_STATUSES:
        raise TaskStatusConflictException(detail="任务已处于终态，无法取消")

    # 取消是请求而非终态：幂等（§13.2「重复取消幂等返回当前终态」）。
    # 若已请求取消，直接返回当前状态，不重复覆盖 cancel_requested_at。
    if task.cancel_requested_at is not None:
        logger.info(
            "任务已请求取消，重复取消幂等返回当前状态: task_id=%s, status=%s",
            task.id,
            task.status,
        )
        return ResearchCancelResponse(
            task_id=task.id,
            status=task.status,
            cancel_requested=True,
        )

    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task.id,
            ResearchTask.status.in_(["pending", "running"]),
            ResearchTask.cancel_requested_at.is_(None),
        )
        .values(cancel_requested_at=now)
    )
    if result.rowcount == 0:
        raise TaskStatusConflictException(detail="任务状态已变更，无法取消")

    # 同步内存对象，避免后续读取到旧状态
    task.cancel_requested_at = now

    logger.info("已请求取消研究任务: task_id=%s, cancel_requested_at=%s", task.id, now)
    return ResearchCancelResponse(
        task_id=task.id,
        status=task.status,
        cancel_requested=True,
    )


# ── 断点续跑（Retry）──────────────────────────────────────────────


# retry 允许的源状态：只有这些状态的任务才可断点续跑。
# canceled 是终态（RESEARCH_PIPELINE §4.1「终态不可恢复为 running」），
# 重新研究必须创建新 Task，不允许从 canceled 恢复。
RETRY_ALLOWED_STATUSES: frozenset[str] = frozenset(
    {
        "failed",
        "partially_completed",
    }
)

# step_type → phase 名称映射（与 pipeline_orchestrator.STEP_TYPE_TO_PHASE 互逆）
_STEP_TYPE_TO_PHASE: dict[str, str] = {
    "planning": "planning",
    "search": "searching",
    "fetch": "fetching",
    "rerank": "reranking",
    "synthesis": "synthesizing",
    "evidence_graph": "building_evidence_graph",
    "render": "rendering",
}

# phase 名称 → step_type 映射
_PHASE_TO_STEP_TYPE: dict[str, str] = {v: k for k, v in _STEP_TYPE_TO_PHASE.items()}


async def retry_task(
    db: AsyncSession,
    task: ResearchTask,
) -> ResearchRetryResponse:
    """断点续跑：从最后 checkpoint 恢复执行。

    对齐 API.md §3.2 POST /api/research/{task_id}/retry：
    - 前置校验：status 必须为 failed / partially_completed / canceled 且 recoverable=true
    - 清理崩溃残留：running → failed（含主 Step 和子 Step）
    - 子 Step 终态化：failed/pending 子 Step → skipped（由 Phase handler 重新创建）
    - 主 Step 重置：failed 主 Step → pending（Orchestrator 重新调度）
    - CAS 更新 task status → pending（复用现有 _run_pipeline / _start_task 流程）
    - 从 execution_context 构建 resume_from 恢复信息

    注意：本函数不提交事务，由 API 层依赖注入的 get_db 统一提交。
    """
    # 1. 前置校验：状态合法性
    if task.status not in RETRY_ALLOWED_STATUSES:
        raise TaskStatusConflictException(
            detail=f"任务当前状态为 {task.status}，不支持 retry 操作",
            current_status=task.status,
            allowed_statuses=list(RETRY_ALLOWED_STATUSES),
        )
    if not task.recoverable:
        raise TaskStatusConflictException(
            detail="该任务不可断点续跑（recoverable=false）",
            current_status=task.status,
        )

    # 2a. 将崩溃残留的 running Step 标记为 failed（含主 Step 和子 Step）
    #     原始执行中崩溃时，Step 可能处于 running 状态而非 failed
    now = datetime.now(timezone.utc)
    running_result = await db.execute(
        sa_update(ResearchStep)
        .where(
            ResearchStep.task_id == task.id,
            ResearchStep.status == "running",
        )
        .values(
            status="failed",
            error_code="E3999",
            error_message="任务中断，Step 被放弃",
            completed_at=now,
        )
    )
    if running_result.rowcount > 0:
        logger.info(
            "重试前清理残留 running Step: task_id=%s, count=%d",
            task.id,
            running_result.rowcount,
        )

    # 2b. 将子 Step（parent_step_id 非空）中仍非终态的标记为 skipped
    #     子 Step 由 Phase handler 内部管理，不应被 Orchestrator 调度执行
    child_cleanup_result = await db.execute(
        sa_update(ResearchStep)
        .where(
            ResearchStep.task_id == task.id,
            ResearchStep.parent_step_id.is_not(None),
            ResearchStep.status.in_(["failed", "pending"]),
        )
        .values(status="skipped")
    )
    if child_cleanup_result.rowcount > 0:
        logger.info(
            "重试前清理残留子 Step: task_id=%s, count=%d",
            task.id,
            child_cleanup_result.rowcount,
        )

    # 2c. 重置因崩溃遗留幂等锁被跳过的主 Step：skipped → pending
    #     这些 Step 的输出 reason 为 "幂等锁已被占用（可能重复入队）"，并非正常跳过，
    #     必须恢复为 pending，否则 retry 后 Rerank/Synthesis 仍会被跳过。
    lock_skip_reason = "幂等锁已被占用（可能重复入队）"
    skip_steps_result = await db.execute(
        select(ResearchStep).where(
            ResearchStep.task_id == task.id,
            ResearchStep.status == "skipped",
            ResearchStep.parent_step_id.is_(None),
        )
    )
    reset_skip_count = 0
    for step in skip_steps_result.scalars().all():
        if isinstance(step.output, dict) and step.output.get("reason") == lock_skip_reason:
            step.status = "pending"
            step.output = None
            step.error_code = None
            step.error_message = None
            reset_skip_count += 1
    if reset_skip_count > 0:
        logger.info(
            "重试前重置锁跳过主 Step: task_id=%s, count=%d",
            task.id,
            reset_skip_count,
        )

    # 2d. 重置主 Step（parent_step_id 为空）：failed → pending
    #     Orchestrator._create_step 只调度主 Step，子 Step 由 Phase handler 重新创建
    reset_result = await db.execute(
        sa_update(ResearchStep)
        .where(
            ResearchStep.task_id == task.id,
            ResearchStep.status == "failed",
            ResearchStep.parent_step_id.is_(None),
        )
        .values(status="pending", error_code=None, error_message=None)
    )
    reset_count = reset_result.rowcount + reset_skip_count
    if reset_count > 0:
        logger.info(
            "重试前重置主 Step: task_id=%s, count=%d",
            task.id,
            reset_count,
        )

    # 3. CAS 更新 task status → pending
    #    （利用现有 _run_pipeline / _start_task 的 pending→running CAS 流程）
    old_status = task.status
    result = await db.execute(
        sa_update(ResearchTask)
        .where(
            ResearchTask.id == task.id,
            ResearchTask.status == old_status,
        )
        .values(
            status="pending",
            current_phase=None,
            error_code=None,
            error_message=None,
            recoverable=None,
            completed_at=None,
            started_at=now,  # 重置派发时间，供 pending 超时监察使用
        )
    )
    if result.rowcount == 0:
        raise TaskStatusConflictException(detail="任务状态已变更，无法重试")

    # 同步内存对象
    task.status = "pending"

    emit_task_status_transition("pending")

    # 4. 从 execution_context 构建 resume_from
    ec = task.execution_context or {}
    last_step_id = ec.get("last_completed_step_id")
    ep = ec.get("execution_pointer", {}) if isinstance(ec, dict) else {}
    last_phase = ep.get("phase") if isinstance(ep, dict) else None

    # 查找下一个待执行的 step_type
    next_step_type = None
    if last_phase:
        last_step_type = _PHASE_TO_STEP_TYPE.get(last_phase, last_phase)
        try:
            idx = PHASE_ORDER.index(last_step_type)
            if idx + 1 < len(PHASE_ORDER):
                next_step_type = PHASE_ORDER[idx + 1]
        except ValueError:
            pass

    logger.info(
        "断点续跑已启动: task_id=%s, last_phase=%s, next_step_type=%s, reset_failed=%d",
        task.id,
        last_phase,
        next_step_type,
        reset_count,
    )

    return ResearchRetryResponse(
        task_id=task.id,
        status="pending",
        resume_from=ResumeFromSchema(
            phase=last_phase,
            last_completed_step_id=last_step_id,
            next_step_type=next_step_type,
        ),
    )


# ── 删除任务 ────────────────────────────────────────────────────


async def delete_task(
    db: AsyncSession,
    task: ResearchTask,
) -> None:
    """删除研究任务及其全部派生数据。

    [Deviation] 使用 bulk DELETE 绕过 ORM 级联：
    SQLite 异步驱动下，SQLAlchemy ORM 在删除 research_tasks 父行前会尝试
    将子表外键 SET NULL，而 task_id 列为非空，导致 IntegrityError。
    数据库层面已声明 FK ON DELETE CASCADE，bulk delete 由 DB 直接级联清理：
    - research_steps (task_id CASCADE)
    - research_sources (task_id CASCADE)
    - evidence_items (task_id CASCADE)
    - report_sections (task_id CASCADE)
    - section_evidence (间接通过 section/evidence CASCADE)

    调用方需先通过 require_task_accessible 校验权限。
    """
    task_id = task.id
    await db.execute(sa_delete(ResearchTask).where(ResearchTask.id == task_id))
    await db.flush()

    logger.info("研究任务已删除: task_id=%s", task_id)
