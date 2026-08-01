"""Search 阶段 —— Tavily API 多子问题搜索 + URL 去重。

对齐 RESEARCH_PIPELINE.md §3：
- 对 Planning 产出的每个 SubQuestion 调用 Tavily Search API
- 跨子问题 URL 去重（保留首次出现的归属）
- 子 step 管理（每个子问题独立 ResearchStep）
- 失败策略：单子问题可降级 SKIPPED / 全部失败 → E3102
"""

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.cost_tracker import calculate_search_cost_usd
from app.core.exceptions import SearchFailedException
from app.models.research_step import ResearchStep
from app.models.research_source import ResearchSource
from app.models.research_task import ResearchTask
from app.pipeline.sse_bridge import (
    SSEBridge,
    EVENT_STEP_COMPLETED,
    EVENT_STEP_PROGRESS,
    EVENT_STEP_SKIPPED,
    EVENT_STEP_STARTED,
    EVENT_TASK_WARNING,
)

logger = logging.getLogger(__name__)

# 搜索重试策略（config.py 未设对应项，Phase4 评估后添加）
_SEARCH_RETRY_MAX = 2
_SEARCH_RETRY_DELAYS = [1.0, 2.0]  # 指数退避

# research_sources.uk_task_url 索引前缀长度（单位：字符，URL 多为 ASCII）
_URL_UNIQUE_PREFIX_LEN = 255


def _url_unique_key(url: str) -> str:
    """生成与 uk_task_url 唯一索引语义一致的 URL 键。

    uk_task_url 为 (task_id, url) 的唯一索引，且 url 列取前缀 255；
    当两条 URL 前 255 字符相同时会在 DB 层冲突，因此应用层去重需使用
    同样的前缀键。
    """
    return url[:_URL_UNIQUE_PREFIX_LEN]


async def _call_tavily(query: str, api_key: str) -> dict:
    """调用 Tavily Search API 单次查询。

    Args:
        query: 搜索查询字符串
        api_key: Tavily API key

    Returns:
        Tavily API 响应 JSON

    Raises:
        httpx.HTTPError: 网络/API 错误
    """
    url = f"{settings.TAVILY_BASE_URL}/search"

    payload = {
        "query": query,
        "search_depth": settings.TAVILY_SEARCH_DEPTH,
        "max_results": settings.TAVILY_MAX_RESULTS_PER_QUERY,
        "include_answer": False,
        "include_raw_content": False,
        "api_key": api_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def _search_one_sub_question(
    sub_question: str,
    index: int,
    api_key: str,
) -> list[dict]:
    """搜索单个子问题，含重试逻辑。

    Args:
        sub_question: 子问题文本
        index: 子问题序号（1-based，仅用于日志）
        api_key: Tavily API key

    Returns:
        Tavily 搜索结果列表（每条含 url/title/snippet/score）

    Raises:
        RuntimeError: 重试耗尽后仍失败
    """
    last_error: Exception | None = None

    for retry in range(_SEARCH_RETRY_MAX + 1):
        try:
            response = await _call_tavily(sub_question, api_key)
            results = response.get("results", [])
            logger.info(
                "Search 子问题 %d 完成: query=%r, results=%d",
                index, sub_question[:60], len(results),
            )
            return results

        except httpx.HTTPStatusError as e:
            last_error = e
            # 4xx 不重试（API key 错误等）
            if 400 <= e.response.status_code < 500:
                logger.warning(
                    "Search 子问题 %d 客户端错误 %d，不重试: %s",
                    index, e.response.status_code, e,
                )
                raise
            # 5xx 可重试
            if retry < _SEARCH_RETRY_MAX:
                delay = _SEARCH_RETRY_DELAYS[retry]
                logger.warning(
                    "Search 子问题 %d 服务端错误，第 %d/%d 次重试，等待 %.1fs: %s",
                    index, retry + 1, _SEARCH_RETRY_MAX, delay, e,
                )
                await asyncio.sleep(delay)
                continue
            raise RuntimeError(f"Tavily API 服务端错误（重试 {_SEARCH_RETRY_MAX} 次耗尽）") from e

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            if retry < _SEARCH_RETRY_MAX:
                delay = _SEARCH_RETRY_DELAYS[retry]
                logger.warning(
                    "Search 子问题 %d 超时/连接错误，第 %d/%d 次重试，等待 %.1fs: %s",
                    index, retry + 1, _SEARCH_RETRY_MAX, delay, e,
                )
                await asyncio.sleep(delay)
                continue
            raise RuntimeError(f"Tavily API 网络错误（重试 {_SEARCH_RETRY_MAX} 次耗尽）") from e

        except Exception as e:
            last_error = e
            if retry < _SEARCH_RETRY_MAX:
                delay = _SEARCH_RETRY_DELAYS[retry]
                logger.warning(
                    "Search 子问题 %d 未知错误，第 %d/%d 次重试，等待 %.1fs: %s",
                    index, retry + 1, _SEARCH_RETRY_MAX, delay, e,
                )
                await asyncio.sleep(delay)
                continue
            raise RuntimeError(f"Tavily API 未知错误（重试 {_SEARCH_RETRY_MAX} 次耗尽）") from e

    raise RuntimeError(f"Search 子问题 {index} 意外退出") from last_error


def _extract_domain(url: str) -> str:
    """从 URL 提取域名。"""
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


async def run_search(
    task: ResearchTask,
    step: ResearchStep,
    session: AsyncSession,
    sse_bridge: SSEBridge,
) -> dict:
    """执行 Search 阶段。

    1. 读取 Planning 产出的 SubQuestion[]
    2. 对每个 SubQuestion 调用 Tavily Search API（含重试）
    3. 创建子 ResearchStep（每个子问题独立）
    4. 跨子问题 URL 去重
    5. 写入 ResearchSource 行
    6. 失败策略：单子问题可降级 SKIPPED / 全部失败 → E3102

    Returns:
        output dict
    """
    task_id = str(task.id)
    root_step_id = str(step.id)

    # 1. 读取 Planning 输出（显式查询，避免异步 relationship 懒加载）
    sub_questions = await _load_sub_questions(session, task)
    if not sub_questions:
        logger.warning("Search: 无子问题输入，跳过: task_id=%s", task_id)
        return {
            "total_results": 0,
            "after_dedup": 0,
            "sub_question_results": [],
            "sources_created": 0,
            "message": "无子问题输入",
        }

    logger.info("Search 开始: task_id=%s, sub_questions=%d", task_id, len(sub_questions))

    api_key = settings.TAVILY_API_KEY
    if not api_key:
        raise SearchFailedException(detail="TAVILY_API_KEY 未配置")

    # 2. 搜索每个子问题
    all_results: list[dict] = []  # 所有原始结果
    sub_results: list[dict] = []  # 每个子问题的汇总
    seen_url_keys: set[str] = set()  # 按 uk_task_url 前缀去重
    all_skipped = True
    sources_created = 0

    for i, sq in enumerate(sub_questions, 1):
        # 创建子 step
        child_step = await _create_child_step(
            session, task, step, step_type="search",
            label=f"搜索子问题 {i}: {sq[:80]}",
        )
        child_step_id = str(child_step.id)

        # 发射子 step.started
        await sse_bridge.publish(EVENT_STEP_STARTED, {
            "step_id": child_step_id,
            "step_type": "search",
            "label": child_step.label,
            "parent_step_id": root_step_id,
        })

        try:
            results = await _search_one_sub_question(sq, i, api_key)
        except Exception as e:
            logger.warning("Search 子问题 %d 失败: %s", i, e)
            # 子 step → skipped
            await _finish_child_step(session, child_step, "skipped")
            await sse_bridge.publish(EVENT_STEP_SKIPPED, {
                "step_id": child_step_id,
                "reason": f"子问题 {i} 搜索失败: {e}",
            })
            sub_results.append({
                "sub_question": sq,
                "index": i,
                "results_count": 0,
                "status": "skipped",
                "step_id": child_step_id,
                "error": str(e),
            })
            continue

        results_count = len(results)
        await sse_bridge.publish(EVENT_STEP_PROGRESS, {
            "step_id": child_step_id,
            "results_found": results_count,
        })

        if results_count == 0:
            # 子 step → skipped（0 结果）
            await _finish_child_step(session, child_step, "skipped")
            await sse_bridge.publish(EVENT_STEP_SKIPPED, {
                "step_id": child_step_id,
                "reason": f"子问题 {i} 搜索返回 0 结果",
            })
            sub_results.append({
                "sub_question": sq,
                "index": i,
                "results_count": 0,
                "status": "skipped",
                "step_id": child_step_id,
            })
            continue

        # 标记为非全跳过
        all_skipped = False

        # 去重：保留首次出现的归属（按 uk_task_url 前缀去重，避免唯一索引冲突）
        selected_results: list[dict] = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            url_key = _url_unique_key(url)
            if url_key in seen_url_keys:
                continue
            if len(selected_results) >= settings.TAVILY_MAX_RESULTS_PER_QUERY:
                break
            seen_url_keys.add(url_key)
            r["source_sub_question"] = sq
            r["sub_question_index"] = i
            selected_results.append(r)

        all_results.extend(selected_results)

        # 子 step → completed（此时 selected 为去重后的数量，最终可能因全局截断而减少）
        child_output = {
            "sub_question": sq,
            "results_found": results_count,
            "selected": len(selected_results),
            "urls": [r["url"] for r in selected_results],
        }
        await _finish_child_step(session, child_step, "completed", child_output)
        await sse_bridge.publish(EVENT_STEP_COMPLETED, {
            "step_id": child_step_id,
            "results_count": results_count,
            "selected": len(selected_results),
        })

        sub_results.append({
            "sub_question": sq,
            "index": i,
            "results_count": results_count,
            "selected": len(selected_results),
            "status": "completed",
            "step_id": child_step_id,
            "urls": [r["url"] for r in selected_results],
        })

        # 总结果截断
        if len(all_results) >= settings.TAVILY_TOTAL_RESULTS_LIMIT:
            logger.info("Search 达到总结果上限 %d，停止搜索: task_id=%s", settings.TAVILY_TOTAL_RESULTS_LIMIT, task_id)
            break

    # 3. 全部失败检查
    if all_skipped and len(sub_results) > 0:
        raise SearchFailedException(
            detail=f"全部 {len(sub_results)} 个子问题搜索失败或返回 0 结果"
        )

    # 4. 按 Tavily score 降序排序并截断至 25 条
    all_results.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    after_dedup = len(all_results)
    if after_dedup > settings.TAVILY_TOTAL_RESULTS_LIMIT:
        all_results = all_results[:settings.TAVILY_TOTAL_RESULTS_LIMIT]
        after_dedup = settings.TAVILY_TOTAL_RESULTS_LIMIT

    final_urls = {r["url"] for r in all_results}

    # 5. 查询该任务已有的 source URL，避免 Worker 崩溃恢复后重复插入
    existing_result = await session.execute(
        select(ResearchSource.url).where(ResearchSource.task_id == task.id)
    )
    existing_urls = {row[0] for row in existing_result.all()}
    existing_url_keys = {_url_unique_key(url) for url in existing_urls}

    # 6. 写入 ResearchSource 行（fetch_status=None，等待 Fetch 阶段填充）
    for r in all_results:
        url = r["url"]
        if url in existing_urls:
            logger.debug(
                "Source URL 已存在，跳过写入: task_id=%s, url=%s",
                task_id, url,
            )
            continue
        url_key = _url_unique_key(url)
        if url_key in existing_url_keys:
            logger.debug(
                "Source URL 前 %d 字符与已有记录冲突，跳过写入: task_id=%s, url=%s",
                _URL_UNIQUE_PREFIX_LEN, task_id, url,
            )
            continue
        source = ResearchSource(
            task_id=task.id,
            url=url,
            title=r.get("title", "")[:500],
            domain=_extract_domain(url)[:255],
            fetch_status=None,
        )
        session.add(source)
        existing_url_keys.add(url_key)
        sources_created += 1
    await session.flush()

    # 6. 低结果数警告（不阻断）
    if after_dedup < 3:
        await sse_bridge.publish(EVENT_TASK_WARNING, {
            "step_id": root_step_id,
            "error_type": "search_low_results",
            "error_description": f"去重后搜索结果仅 {after_dedup} 条，少于 3 条，可能影响后续报告质量",
        })

    # 7. 修正各子问题的 selected 数量（全局截断后可能减少）
    for sr in sub_results:
        if sr.get("status") == "completed":
            sr["selected"] = len([u for u in sr.get("urls", []) if u in final_urls])
        sr.pop("urls", None)

    # 8. 不覆盖 task.total_sources（其语义为 Fetch 成功抓取数，见 API.md §3.6），
    #    去重后的 URL 数通过 output.total_urls 透传，供后续动态进度计算使用。
    query_count = sum(1 for sr in sub_results if sr.get("status") == "completed")
    search_cost_usd = calculate_search_cost_usd(
        query_count=query_count,
        depth=settings.TAVILY_SEARCH_DEPTH,
    )
    output = {
        "total_results": sum(sr.get("results_count", 0) for sr in sub_results),
        "after_dedup": after_dedup,
        "total_urls": after_dedup,
        "sub_question_results": sub_results,
        "sources_created": sources_created,
        "search_cost_usd": search_cost_usd,
    }

    logger.info(
        "Search 完成: task_id=%s, total=%d, deduped=%d, sources=%d",
        task_id, output["total_results"], after_dedup, sources_created,
    )
    return output


# ── 辅助函数 ──────────────────────────────────────────────────


async def _load_sub_questions(
    session: AsyncSession,
    task: ResearchTask,
) -> list[str]:
    """从 Planning 阶段输出中提取 sub_questions。

    显式查询 research_steps 表，避免在 AsyncSession 中依赖 relationship 懒加载
    触发 MissingGreenlet。
    """
    stmt = (
        select(ResearchStep)
        .where(
            ResearchStep.task_id == task.id,
            ResearchStep.step_type == "planning",
            ResearchStep.status == "completed",
        )
        .order_by(ResearchStep.completed_at)
    )
    result = await session.execute(stmt)
    planning_step: ResearchStep | None = result.scalar_one_or_none()

    if planning_step and planning_step.output and isinstance(planning_step.output, dict):
        sqs = planning_step.output.get("sub_questions", [])
        if isinstance(sqs, list):
            return [str(sq) for sq in sqs if sq]

    return []


async def _create_child_step(
    session: AsyncSession,
    task: ResearchTask,
    parent_step: ResearchStep,
    step_type: str,
    label: str,
) -> ResearchStep:
    """创建子 ResearchStep。"""
    now = datetime.now(timezone.utc)
    child = ResearchStep(
        task_id=task.id,
        step_type=step_type,
        parent_step_id=parent_step.id,
        status="running",
        label=label,
        started_at=now,
    )
    session.add(child)
    await session.flush()
    return child


async def _finish_child_step(
    session: AsyncSession,
    child_step: ResearchStep,
    status: str,
    output: dict | None = None,
) -> None:
    """完成子 step（更新状态 + 耗时 + 输出）。"""
    now = datetime.now(timezone.utc)
    child_step.status = status
    child_step.completed_at = now
    if child_step.started_at:
        delta = now - child_step.started_at
        child_step.duration_ms = int(delta.total_seconds() * 1000)
    if output is not None:
        child_step.output = output
    # 更新 task 完成计数
    await session.flush()
