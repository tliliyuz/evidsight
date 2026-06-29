"""Phase4 断点续跑集成测试辅助函数。

提供数据工厂、mock 上下文、断言辅助等可复用工具。
"""
import contextlib
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMResult
from app.core.security import hash_password
from app.models.evidence_item import EvidenceItem
from app.models.report_section import ReportSection
from app.models.research_source import ResearchSource
from app.models.research_step import ResearchStep
from app.models.research_task import ResearchTask
from app.models.section_evidence import SectionEvidence
from app.models.user import User
from app.pipeline.reranker import Evidence
from app.pipeline.synthesizer import ConflictPosition, SynthesisCluster, SynthesisConflict, SynthesisNotes


# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

PHASE_ORDER = ["planning", "search", "fetch", "rerank", "synthesis", "evidence_graph", "render"]

PHASE_LABELS = {
    "planning": "Planning：拆解研究主题",
    "search": "Search：多子问题搜索",
    "fetch": "Fetch：网页内容抓取",
    "rerank": "Rerank：来源粗筛精排",
    "synthesis": "Synthesis：跨源综合",
    "evidence_graph": "来源图谱：结构化认知资产构建",
    "render": "Render：报告渲染",
}

PHASE_TO_STEP_TYPE = {
    "planning": "planning",
    "searching": "search",
    "fetching": "fetch",
    "reranking": "rerank",
    "synthesizing": "synthesis",
    "building_evidence_graph": "evidence_graph",
    "rendering": "render",
}

STEP_TYPE_TO_PHASE = {v: k for k, v in PHASE_TO_STEP_TYPE.items()}


# ═══════════════════════════════════════════════════════════════
# LLM / Pipeline 结果工厂
# ═══════════════════════════════════════════════════════════════


def _make_llm_result(content: str, prompt_tokens: int = 100, completion_tokens: int = 50) -> LLMResult:
    """构造 LLMResult。"""
    return LLMResult(
        content=content,
        reasoning_content="",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _valid_planning_json() -> str:
    """返回有效的 Planning 输出 JSON（需满足 3-5 个子问题校验）。"""
    return json.dumps({
        "sub_questions": [
            "量子计算对 RSA/ECC 的具体威胁",
            "NIST 后量子密码标准化最新进展",
            "中国在量子安全通信领域的政策与布局",
        ],
        "rationale": "从技术威胁、标准应对、政策布局三维度拆解",
    }, ensure_ascii=False)


def _build_tavily_side_effect():
    """构造 Search 阶段 Tavily Mock side_effect。"""
    async def _side_effect(query: str, api_key: str) -> dict:
        prefix = "threat" if "RSA" in query or "ECC" in query else "standard"
        return {
            "results": [
                {
                    "url": f"https://example.com/{prefix}-article{i}",
                    "title": f"{prefix.title()} Article {i}",
                    "score": 0.95 - i * 0.05,
                }
                for i in range(1, 3)
            ],
        }
    return _side_effect


def _build_fetch_side_effect(*, failing_url: str | None = None, fail_status: str = "timeout"):
    """构造 Fetch 阶段 HTTP Mock side_effect。

    Args:
        failing_url: 指定要失败的 URL，返回 fail_status 对应的状态。
        fail_status: 失败状态，可选 timeout / blocked / empty / dns_error。
    """
    async def _side_effect(url: str) -> dict:
        if failing_url and url == failing_url:
            if fail_status == "timeout":
                return {"status": "timeout", "content": None, "content_length": None, "error": "请求超时"}
            if fail_status == "blocked":
                return {"status": "blocked", "content": None, "content_length": None, "error": "HTTP 403"}
            if fail_status == "empty":
                return {"status": "empty", "content": None, "content_length": None, "error": "正文为空"}
            if fail_status == "dns_error":
                return {"status": "dns_error", "content": None, "content_length": None, "error": "DNS 失败"}
        return {
            "status": "success",
            "content": f"# {url.split('/')[-1]} 标题\n\n这是关于 {url} 的正文，"
                       f"包含量子计算和网络安全相关信息，用于测试报告生成。",
            "content_length": 180,
        }
    return _side_effect


def _build_rerank_side_effect(db_session: AsyncSession, task_id: str):
    """构造 Rerank 阶段 Mock side_effect：基于真实 DB 中的 ResearchSource 生成 Evidence。"""
    async def _side_effect(topic: str, task_type: str, sub_questions: list[str], candidates: list):
        result = await db_session.execute(
            select(ResearchSource).where(
                ResearchSource.task_id == task_id,
                ResearchSource.fetch_status == "success",
            )
        )
        sources = list(result.scalars().all())
        evidence_list = []
        for i, source in enumerate(sources):
            evidence_list.append(Evidence(
                source_id=source.id,
                url=source.url,
                title=source.title or "",
                domain=source.domain or "",
                content=source.content or "",
                relevance_score=round(0.9 - i * 0.05, 3),
                bm25_score=1.0,
                sub_question_index=0,
                word_count=len(source.content or ""),
                rationale="与问题高度相关",
            ))
        evidence_list.sort(key=lambda e: e.relevance_score, reverse=True)
        return evidence_list, 500, 200, 0
    return _side_effect


def _build_synthesis_side_effect():
    """构造 Synthesis 阶段 Mock side_effect。"""
    async def _side_effect(topic: str, task_type: str, evidence_items_formatted: str, evidence_count: int):
        notes = SynthesisNotes(
            clusters=[
                SynthesisCluster(
                    theme="量子计算威胁",
                    summary="量子计算对 RSA 和 ECC 构成实际威胁。",
                    consensus_level="strong",
                    supporting_evidence_indices=[0, 1],
                    conflicting_evidence_indices=[],
                ),
                SynthesisCluster(
                    theme="后量子密码标准化",
                    summary="NIST 正在推进后量子密码标准制定。",
                    consensus_level="moderate",
                    supporting_evidence_indices=[2],
                    conflicting_evidence_indices=[],
                ),
            ],
            conflicts=[
                SynthesisConflict(
                    topic="标准化时间表分歧",
                    position_a=ConflictPosition("NIST 2024 年发布最终标准", [0]),
                    position_b=ConflictPosition("业界认为需更长时间验证", [1]),
                ),
            ],
            knowledge_gaps=["量子计算机实际错误率数据", "大规模商用时间表"],
            overall_assessment="证据质量较高，但缺少具体量化数据。",
        )
        return notes, 1000, 500, 0
    return _side_effect


def _build_render_side_effect():
    """构造 Render 阶段 Mock side_effect：返回包含 [来源N] 引用的报告。"""
    async def _side_effect(messages: list[dict[str, str]]) -> tuple[str, LLMResult, int]:
        raw_text = json.dumps({
            "sections": [
                {
                    "heading": "1. 概述",
                    "content": "量子计算对 RSA 构成威胁[来源0]，NIST 推进后量子密码标准化[来源1]。",
                },
                {
                    "heading": "2. 威胁分析",
                    "content": "Shor 算法可分解大整数[来源0]，威胁现有公钥体系[来源2]。",
                },
                {
                    "heading": "3. 应对策略",
                    "content": "推进后量子密码迁移是当务之急[来源1]，需制定分阶段路线图[来源2]。",
                },
            ],
        }, ensure_ascii=False)
        return raw_text, _make_llm_result(raw_text, prompt_tokens=2000, completion_tokens=1500), 0
    return _side_effect


# ═══════════════════════════════════════════════════════════════
# 数据工厂
# ═══════════════════════════════════════════════════════════════


async def _seed_user(db_session: AsyncSession) -> User:
    """预置测试用户（id=1），如已存在则返回已有用户。"""
    existing = await db_session.execute(select(User).where(User.id == 1))
    user = existing.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        id=1,
        username="testuser",
        password_hash=hash_password("testpass123"),
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_task(
    db_session: AsyncSession,
    *,
    task_id: str | None = None,
    status: str = "pending",
    execution_context: dict | None = None,
    trace: dict | None = None,
    recoverable: bool | None = None,
    error_code: str | None = None,
    started_at: datetime | None = None,
) -> ResearchTask:
    """预置一个基础任务。"""
    await _seed_user(db_session)
    task = ResearchTask(
        id=task_id,
        user_id=1,
        topic="量子计算对网络安全的威胁与应对策略",
        requirements={
            "task_type": "analysis",
            "depth": "quick",
            "max_sources": 5,
            "language": "zh",
        },
        status=status,
        total_steps=7,
        completed_steps=0,
        total_sources=0,
        total_evidence=0,
        execution_context=execution_context,
        trace=trace,
        recoverable=recoverable,
        error_code=error_code,
        error_message=None,
        started_at=started_at,
    )
    db_session.add(task)
    await db_session.flush()
    return task


async def _create_step(
    db_session: AsyncSession,
    task_id: str,
    step_type: str,
    *,
    status: str = "pending",
    parent_step_id: str | None = None,
    output: dict | None = None,
    error_code: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
) -> ResearchStep:
    """创建一个 Step 并返回。"""
    step = ResearchStep(
        task_id=task_id,
        step_type=step_type,
        parent_step_id=parent_step_id,
        status=status,
        label=PHASE_LABELS.get(step_type, step_type),
        output=output,
        error_code=error_code,
        error_message=None,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )
    db_session.add(step)
    await db_session.flush()
    return step


async def _seed_sources_and_evidence(
    db_session: AsyncSession,
    task_id: str,
    *,
    count: int = 4,
    step_id: str | None = None,
    create_evidence: bool = True,
) -> tuple[list[ResearchSource], list[EvidenceItem]]:
    """预置 ResearchSource 与 EvidenceItem，供已完成的 Search/Fetch/Rerank 阶段使用。

    同一任务多次调用时，Source 只创建一次；Evidence 是否创建由 create_evidence 控制。

    Returns:
        (sources, evidence_items)
    """
    result = await db_session.execute(
        select(ResearchSource).where(ResearchSource.task_id == task_id)
    )
    sources = list(result.scalars().all())

    if not sources:
        for i in range(count):
            prefix = "threat" if i < 2 else "standard"
            source = ResearchSource(
                task_id=task_id,
                url=f"https://example.com/{prefix}-article{i + 1}",
                title=f"{prefix.title()} Article {i + 1}",
                domain="example.com",
                fetch_status="success",
                content=f"# {prefix} article {i + 1}\n\n量子计算与网络安全测试正文，用于断点续跑。",
                fetched_at=datetime.now(timezone.utc),
            )
            db_session.add(source)
            sources.append(source)
        await db_session.flush()

    evidence_items: list[EvidenceItem] = []
    if create_evidence:
        for i, source in enumerate(sources):
            item = EvidenceItem(
                task_id=task_id,
                source_id=source.id,
                step_id=step_id,
                content=source.content or "",
                relevance_score=round(0.9 - i * 0.05, 3),
            )
            db_session.add(item)
            evidence_items.append(item)
        await db_session.flush()

    return sources, evidence_items


def _make_planning_output() -> dict:
    """构造合法的 Planning Step output。"""
    return {
        "sub_questions": [
            "量子计算对 RSA/ECC 的具体威胁",
            "NIST 后量子密码标准化最新进展",
            "中国在量子安全通信领域的政策与布局",
        ],
        "rationale": "从技术威胁、标准应对、政策布局三维度拆解",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "model": "gpt-4o-mini",
    }


def _make_synthesis_output() -> dict:
    """构造合法的 Synthesis Step output。"""
    return {
        "clusters": [
            {
                "theme": "量子计算威胁",
                "summary": "量子计算对 RSA 和 ECC 构成实际威胁。",
                "consensus_level": "strong",
                "supporting_evidence_indices": [0, 1],
                "conflicting_evidence_indices": [],
            },
            {
                "theme": "后量子密码标准化",
                "summary": "NIST 正在推进后量子密码标准制定。",
                "consensus_level": "moderate",
                "supporting_evidence_indices": [2],
                "conflicting_evidence_indices": [],
            },
        ],
        "conflicts": [
            {
                "topic": "标准化时间表分歧",
                "position_a": {"summary": "NIST 2024 年发布最终标准", "evidence_indices": [0]},
                "position_b": {"summary": "业界认为需更长时间验证", "evidence_indices": [1]},
            },
        ],
        "knowledge_gaps": ["量子计算机实际错误率数据", "大规模商用时间表"],
        "overall_assessment": "证据质量较高，但缺少具体量化数据。",
        "clusters_count": 2,
        "conflicts_count": 1,
        "gaps_count": 2,
        "model": "gpt-4o-mini",
        "retry_count": 0,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "evidence_count": 4,
    }


def _make_evidence_graph_output(evidence_items: list[EvidenceItem]) -> dict:
    """构造合法的 Evidence Graph Step output。"""
    items = []
    clusters: dict[str, dict] = {}
    for i, ev in enumerate(evidence_items):
        item = {
            "index": i,
            "evidence_item_id": ev.id,
            "source_id": ev.source_id,
            "source_url": ev.source.url if ev.source else "",
            "source_title": ev.source.title if ev.source else "",
            "domain": ev.source.domain if ev.source else "example.com",
            "content": ev.content,
            "relevance_score": float(ev.relevance_score) if ev.relevance_score else 0.9,
            "cluster_theme": "量子计算威胁" if i < 2 else "后量子密码标准化",
            "consensus_level": "strong" if i < 2 else "moderate",
            "used_in_sections": [],
        }
        items.append(item)
        theme = item["cluster_theme"]
        if theme not in clusters:
            clusters[theme] = {
                "theme": theme,
                "summary": "测试聚类",
                "consensus_level": item["consensus_level"],
                "evidence_indices": [],
            }
        clusters[theme]["evidence_indices"].append(i)

    graph = {
        "task_id": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "clusters": list(clusters.values()),
        "conflicts": [
            {
                "topic": "标准化时间表分歧",
                "position_a": {"summary": "NIST 2024 年发布最终标准", "evidence_indices": [0]},
                "position_b": {"summary": "业界认为需更长时间验证", "evidence_indices": [1]},
            },
        ],
        "knowledge_gaps": ["量子计算机实际错误率数据", "大规模商用时间表"],
        "sources": [
            {
                "id": ev.source_id,
                "url": ev.source.url if ev.source else "",
                "title": ev.source.title if ev.source else "",
                "domain": ev.source.domain if ev.source else "example.com",
                "evidence_count": 1,
            }
            for ev in evidence_items
        ],
    }
    return {
        "graph": graph,
        "item_count": len(items),
        "cluster_count": len(clusters),
        "conflict_count": 1,
        "source_count": len(evidence_items),
        "duration_ms": 1000,
    }


def _make_generic_step_output() -> dict:
    """构造通用已完成 Step output（用于不直接产出下游数据的阶段）。"""
    return {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "model": "gpt-4o-mini",
    }


async def _seed_failed_task(
    db_session: AsyncSession,
    *,
    completed_through: str | None = None,
    failed_at: str,
    recoverable: bool = True,
    error_code: str = "E3104",
) -> ResearchTask:
    """预置一个失败任务，指定已完成阶段和失败阶段。

    Args:
        completed_through: 已完成的阶段名称（含）之前的所有 PHASE_ORDER 阶段均为 completed。
        failed_at: 失败阶段名称，该阶段主 Step 为 failed。
        recoverable: 是否可恢复。
        error_code: 失败错误码。
    """
    task = await _seed_task(db_session, status="failed", recoverable=recoverable, error_code=error_code)
    last_completed_step_id = None
    last_phase = None
    completed_idx = -1

    sources: list[ResearchSource] = []
    evidence_items: list[EvidenceItem] = []

    if completed_through:
        completed_idx = PHASE_ORDER.index(completed_through)
        for i, step_type in enumerate(PHASE_ORDER[: completed_idx + 1]):
            now = datetime.now(timezone.utc)
            output: dict | None = None

            if step_type == "planning":
                output = _make_planning_output()
            elif step_type in ("search", "fetch"):
                # Search/Fetch 的 output 使用通用格式；真实数据在 research_sources 表
                output = _make_generic_step_output()
            elif step_type == "rerank":
                output = _make_generic_step_output()
            elif step_type == "synthesis":
                output = _make_synthesis_output()
            elif step_type == "evidence_graph":
                output = _make_evidence_graph_output(evidence_items)
            elif step_type == "render":
                output = _make_generic_step_output()

            step = await _create_step(
                db_session,
                task.id,
                step_type,
                status="completed",
                output=output,
                started_at=now - timedelta(seconds=10),
                completed_at=now,
                duration_ms=1000,
            )
            last_completed_step_id = step.id
            last_phase = STEP_TYPE_TO_PHASE[step_type]

            # 为 completed 阶段补充真实下游数据
            if step_type == "fetch":
                # fetch 完成后应存在带内容的 source（Evidence 在 rerank 阶段创建）
                sources, _ = await _seed_sources_and_evidence(db_session, task.id, count=4, create_evidence=False)
                # 将 source 与 fetch step 关联（rerank 读取 source 表，不依赖 step_id）
                for src in sources:
                    src.fetched_at = now
            elif step_type == "rerank":
                # rerank 完成后应存在 EvidenceItem
                _, evidence_items = await _seed_sources_and_evidence(db_session, task.id, count=4, step_id=step.id)
            elif step_type == "synthesis":
                # synthesis 完成后 evidence_graph 会读取 synthesis output
                pass
            elif step_type == "evidence_graph":
                # evidence_graph 完成后 render 会读取 graph output
                pass

    failed_step = await _create_step(
        db_session,
        task.id,
        failed_at,
        status="failed",
        error_code=error_code,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        completed_at=datetime.now(timezone.utc),
        duration_ms=500,
    )

    # 构造 execution_context：last_completed_step_id 指向 completed_through 阶段，
    # 若 completed_through 为空则指向失败阶段的前一个阶段不存在，此时 next_step_type=None，
    # Orchestrator 会从第一个阶段开始执行。
    ec: dict = {}
    if last_completed_step_id:
        ec = {
            "current_phase": last_phase,
            "last_completed_step_id": last_completed_step_id,
            "execution_pointer": {
                "phase": last_phase,
                "step_index": 1,
                "total_steps_in_phase": 1,
            },
            "progress": {
                "completed_steps": completed_idx + 1,
                "total_steps": 7,
                "progress": round((completed_idx + 1) / 7, 2),
            },
        }

    # 构造 trace：包含已完成阶段的数据
    trace_phases = {}
    if completed_through:
        end_idx = PHASE_ORDER.index(completed_through)
        for step_type in PHASE_ORDER[: end_idx + 1]:
            trace_phases[step_type] = {
                "span_name": step_type,
                "duration_ms": 1000,
                "status": "success",
                "input_tokens": 100,
                "output_tokens": 50,
                "model": "gpt-4o-mini",
            }

    task.execution_context = ec
    task.trace = {
        "task_id": task.id,
        "user_id": 1,
        "status": "error",
        "total_duration_ms": 1000 * len(trace_phases),
        "total_input_tokens": 100 * len(trace_phases),
        "total_output_tokens": 50 * len(trace_phases),
        "total_tokens": 150 * len(trace_phases),
        "total_cost_usd": 0.001 * len(trace_phases),
        "phases": trace_phases,
        "phase_durations_ms": {k: 1000 for k in trace_phases},
        "breakdown": {k: {"tokens": 150, "cost": 0.001} for k in trace_phases},
        "error_message": "模拟失败",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db_session.flush()
    return task


async def _seed_crash_task(
    db_session: AsyncSession,
    *,
    crash_after: str,
    started_seconds_ago: int = 120,
) -> ResearchTask:
    """预置一个 Worker 崩溃残留任务。

    Args:
        crash_after: 崩溃前已完成的阶段名称，该阶段及之前为 completed，
                     下一阶段主 Step 为 running（模拟崩溃残留）。
        started_seconds_ago: started_at 距离现在的秒数，用于触发超时检测。
    """
    crash_idx = PHASE_ORDER.index(crash_after)
    next_step_type = PHASE_ORDER[crash_idx + 1] if crash_idx + 1 < len(PHASE_ORDER) else None

    execution_context = {}
    trace_phases = {}
    last_completed_step_id = None
    last_phase = None

    task = await _seed_task(
        db_session,
        status="running",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=started_seconds_ago),
    )

    sources: list[ResearchSource] = []
    evidence_items: list[EvidenceItem] = []

    for i, step_type in enumerate(PHASE_ORDER[: crash_idx + 1]):
        now = datetime.now(timezone.utc) - timedelta(seconds=started_seconds_ago - i * 10)
        output: dict | None = None

        if step_type == "planning":
            output = _make_planning_output()
        elif step_type in ("search", "fetch"):
            output = _make_generic_step_output()
        elif step_type == "rerank":
            output = _make_generic_step_output()
        elif step_type == "synthesis":
            output = _make_synthesis_output()
        elif step_type == "evidence_graph":
            output = _make_evidence_graph_output(evidence_items)
        elif step_type == "render":
            output = _make_generic_step_output()

        step = await _create_step(
            db_session,
            task.id,
            step_type,
            status="completed",
            output=output,
            started_at=now,
            completed_at=now + timedelta(seconds=5),
            duration_ms=5000,
        )
        last_completed_step_id = step.id
        last_phase = STEP_TYPE_TO_PHASE[step_type]
        trace_phases[step_type] = {
            "span_name": step_type,
            "duration_ms": 5000,
            "status": "success",
            "input_tokens": 100,
            "output_tokens": 50,
            "model": "gpt-4o-mini",
        }

        if step_type == "fetch":
            sources, _ = await _seed_sources_and_evidence(db_session, task.id, count=4, create_evidence=False)
            for src in sources:
                src.fetched_at = now
        elif step_type == "rerank":
            _, evidence_items = await _seed_sources_and_evidence(db_session, task.id, count=4, step_id=step.id)

    # crash 发生在 search 后，fetch 阶段会被重新执行；需要预置待抓取的 source
    if crash_after == "search":
        await _seed_sources_and_evidence(db_session, task.id, count=4, create_evidence=False)

    if next_step_type:
        await _create_step(
            db_session,
            task.id,
            next_step_type,
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=started_seconds_ago - (crash_idx + 1) * 10),
        )

    execution_context = {
        "current_phase": last_phase,
        "last_completed_step_id": last_completed_step_id,
        "execution_pointer": {
            "phase": last_phase,
            "step_index": 1,
            "total_steps_in_phase": 1,
        },
        "progress": {
            "completed_steps": crash_idx + 1,
            "total_steps": 7,
            "progress": round((crash_idx + 1) / 7, 2),
        },
    }

    task.execution_context = execution_context
    task.trace = {
        "task_id": task.id,
        "user_id": 1,
        "status": "success",
        "total_duration_ms": 5000 * len(trace_phases),
        "total_input_tokens": 100 * len(trace_phases),
        "total_output_tokens": 50 * len(trace_phases),
        "total_tokens": 150 * len(trace_phases),
        "total_cost_usd": 0.001 * len(trace_phases),
        "phases": trace_phases,
        "phase_durations_ms": {k: 5000 for k in trace_phases},
        "breakdown": {k: {"tokens": 150, "cost": 0.001} for k in trace_phases},
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db_session.flush()
    return task


# ═══════════════════════════════════════════════════════════════
# Session 工厂包装（用于 _run_pipeline / recover_stale_tasks 等）
# ═══════════════════════════════════════════════════════════════


class _SessionContextManager:
    """把已存在的 db_session 包装成 async_session_factory 的上下文管理器。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(db_session: AsyncSession):
    """返回一个复用测试 db_session 的 session_factory。"""
    def factory():
        return _SessionContextManager(db_session)
    return factory


# ═══════════════════════════════════════════════════════════════
# Mock 上下文与记录器
# ═══════════════════════════════════════════════════════════════


@contextlib.asynccontextmanager
async def _commit_to_flush(session: AsyncSession):
    """将 session.commit 重定向为 flush，保证集成测试事务隔离。"""
    original_commit = session.commit

    async def _flush():
        await session.flush()

    session.commit = _flush
    try:
        yield
    finally:
        session.commit = original_commit


def _record_sse_events(sse_bridge):
    """替换 SSEBridge.publish 为记录器，返回事件列表。"""
    published_events: list[tuple[str, dict | None]] = []

    async def _capture(event_type, data=None):
        published_events.append((event_type, data))

    sse_bridge.publish = AsyncMock(side_effect=_capture)
    return published_events


def _mock_pipeline_external(
    db_session: AsyncSession,
    task_id: str,
    *,
    fail_at: str | None = None,
    failing_url: str | None = None,
) -> list:
    """集成测试专用：mock 所有外部依赖，保留 Orchestrator 真实调度逻辑。

    Returns:
        patches 列表，调用方需用 ExitStack 自行管理生命周期。
    """
    from app.core.exceptions import AppException

    class _FailingPhaseException(AppException):
        error_code = "E3999"
        default_message = "模拟阶段失败"

        def __init__(self, phase: str):
            super().__init__(detail=f"模拟 {phase} 阶段失败")
            self.phase = phase

    async def _failing_handler(*args, **kwargs):
        raise _FailingPhaseException(fail_at)

    patches = [
        patch("app.pipeline.planner.chat_completion", return_value=_make_llm_result(_valid_planning_json())),
        patch("app.pipeline.searcher._call_tavily", side_effect=_build_tavily_side_effect()),
        patch("app.pipeline.fetcher._fetch_one_url", side_effect=_build_fetch_side_effect(failing_url=failing_url)),
        patch("app.pipeline.reranker._llm_rerank", side_effect=_build_rerank_side_effect(db_session, task_id)),
        patch("app.pipeline.synthesizer._llm_synthesize", side_effect=_build_synthesis_side_effect()),
        patch("app.pipeline.renderer._call_llm_render", side_effect=_build_render_side_effect()),
        # URL 安全检查：直接放行，避免测试中进行真实 DNS 解析
        patch("app.pipeline.fetcher.check_url_safety", new_callable=AsyncMock, return_value=None),
        # Redis 锁：全部放行（Orchestrator 从 app.services.pipeline_orchestrator 导入）
        patch("app.services.pipeline_orchestrator.acquire_step_lock_async", return_value=True),
        patch("app.services.pipeline_orchestrator.release_step_lock_async", new_callable=AsyncMock),
        patch("app.services.pipeline_orchestrator.acquire_task_lock_async", return_value=True),
        patch("app.services.pipeline_orchestrator.release_task_lock_async", new_callable=AsyncMock),
        patch("app.services.pipeline_orchestrator.refresh_task_lock_async", new_callable=AsyncMock),
        patch("app.services.pipeline_orchestrator.check_task_lock_async", return_value=False),
    ]

    if fail_at == "planning":
        patches[0] = patch("app.pipeline.planner.chat_completion", side_effect=_failing_handler)
    elif fail_at == "search":
        patches[1] = patch("app.pipeline.searcher._call_tavily", side_effect=_failing_handler)
    elif fail_at == "fetch":
        patches[2] = patch("app.pipeline.fetcher._fetch_one_url", side_effect=_failing_handler)
    elif fail_at == "rerank":
        patches[3] = patch("app.pipeline.reranker._llm_rerank", side_effect=_failing_handler)
    elif fail_at == "synthesis":
        patches[4] = patch("app.pipeline.synthesizer._llm_synthesize", side_effect=_failing_handler)
    elif fail_at == "evidence_graph":
        # evidence_graph 为纯程序化步骤，不调用 LLM；通过让 renderer 失败来间接模拟并不合理。
        # 此处保留占位：让 synthesis output 读取失败或 renderer 提前失败。
        patches[4] = patch("app.pipeline.synthesizer._llm_synthesize", side_effect=_failing_handler)
    elif fail_at == "render":
        patches[5] = patch("app.pipeline.renderer._call_llm_render", side_effect=_failing_handler)

    return patches


# ═══════════════════════════════════════════════════════════════
# 断言辅助
# ═══════════════════════════════════════════════════════════════


async def _assert_main_step_status(
    db_session: AsyncSession,
    task_id: str,
    expected: dict[str, str],
) -> None:
    """验证任务主 Step 状态。

    主 Step 判定与 Orchestrator._create_step 一致：
    - parent_step_id IS NULL（首个主 Step）
    - 或 parent_step.step_type != 当前 step_type（链式 Phase 主 Step）
    """
    parent_step = aliased(ResearchStep)
    result = await db_session.execute(
        select(ResearchStep)
        .outerjoin(
            parent_step,
            ResearchStep.parent_step_id == parent_step.id,
        )
        .where(
            ResearchStep.task_id == task_id,
            ResearchStep.step_type.in_(expected.keys()),
            or_(
                ResearchStep.parent_step_id.is_(None),
                parent_step.step_type != ResearchStep.step_type,
            ),
        )
    )
    actual = {s.step_type: s.status for s in result.scalars().all()}
    assert actual == expected, f"主 Step 状态不匹配: expected={expected}, actual={actual}"


async def _get_task(db_session: AsyncSession, task_id: str) -> ResearchTask:
    """获取任务并验证存在。"""
    task = await db_session.get(ResearchTask, task_id)
    assert task is not None, f"任务 {task_id} 不存在"
    return task


async def _assert_evidence_count(db_session: AsyncSession, task_id: str, expected: int) -> None:
    """验证 EvidenceItem 数量。"""
    count = await db_session.scalar(
        select(func.count()).select_from(EvidenceItem).where(EvidenceItem.task_id == task_id)
    )
    assert count == expected, f"EvidenceItem 数量不匹配: expected={expected}, actual={count}"


async def _assert_sources_count(db_session: AsyncSession, task_id: str, expected: int) -> None:
    """验证 ResearchSource 成功数量。"""
    count = await db_session.scalar(
        select(func.count())
        .select_from(ResearchSource)
        .where(
            ResearchSource.task_id == task_id,
            ResearchSource.fetch_status == "success",
        )
    )
    assert count == expected, f"成功 Source 数量不匹配: expected={expected}, actual={count}"


async def _assert_report_sections_exist(db_session: AsyncSession, task_id: str, expected_count: int) -> None:
    """验证 ReportSection 已写入。"""
    count = await db_session.scalar(
        select(func.count()).select_from(ReportSection).where(ReportSection.task_id == task_id)
    )
    assert count == expected_count, f"ReportSection 数量不匹配: expected={expected_count}, actual={count}"

    if expected_count > 0:
        se_count = await db_session.scalar(
            select(func.count())
            .select_from(SectionEvidence)
            .join(ReportSection, SectionEvidence.section_id == ReportSection.id)
            .where(ReportSection.task_id == task_id)
        )
        assert se_count > 0, "ReportSection 存在但无 SectionEvidence 关联"
