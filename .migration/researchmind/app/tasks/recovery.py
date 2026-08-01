"""Worker 崩溃恢复逻辑。

提供启动恢复和 Worker 就绪恢复两种入口：
- 启动恢复：FastAPI lifespan 启动时调用
- Worker 就绪恢复：Celery Worker 启动完成时调用

恢复条件：
1. task.status == 'running'
2. started_at 超过 STALE_TASK_RECOVERY_SECONDS 阈值
3. 任务级锁不存在（说明无活跃 Worker 在执行）

满足条件则重新投递 execute_research_task，由修复后的 _run_pipeline + _start_task
处理恢复路径。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select as sa_select

from app.config import settings
from app.core.database import async_session_factory
from app.models.research_task import ResearchTask
from app.tasks.lock import check_task_lock_async

logger = logging.getLogger(__name__)


async def recover_stale_tasks(check_lock: bool = True) -> list[str]:
    """扫描并恢复过时 running 任务。

    Args:
        check_lock: 是否检查任务级锁。True 时只有锁不存在才恢复；
                    False 时仅按时间阈值恢复（用于启动恢复兜底）。

    Returns:
        重新投递的任务 ID 列表
    """
    recovered: list[str] = []
    if not settings.STARTUP_RECOVERY_ENABLED:
        return recovered

    try:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.STALE_TASK_RECOVERY_SECONDS)
        async with async_session_factory() as session:
            result = await session.execute(
                sa_select(ResearchTask.id)
                .where(
                    ResearchTask.status == "running",
                    ResearchTask.started_at < threshold,
                )
                .order_by(ResearchTask.started_at)
            )
            candidate_ids = [row[0] for row in result.all()]
    except Exception:
        logger.exception("扫描过时 running 任务失败")
        return recovered

    if not candidate_ids:
        logger.info("未发现过时 running 任务")
        return recovered

    # 局部导入避免循环依赖
    from app.tasks.research_task import execute_research_task

    for task_id in candidate_ids:
        try:
            if check_lock:
                lock_exists = await check_task_lock_async(task_id)
                if lock_exists:
                    logger.info(
                        "任务级锁仍存在，跳过恢复（可能仍有 Worker 执行）: task_id=%s",
                        task_id,
                    )
                    continue

            execute_research_task.delay(task_id)
            recovered.append(str(task_id))
            logger.warning("已重新投递过时任务: task_id=%s", task_id)
        except Exception:
            logger.exception("重新投递过时任务失败: task_id=%s", task_id)

    return recovered
