import logging
import sys

from celery import Celery
from celery.signals import worker_ready

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "researchmind",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # 队列路由必须与部署侧 Worker 的显式监听队列一致。
    task_default_queue=settings.CELERY_EXECUTE_QUEUE,
    task_routes={
        "execute_research_task": {"queue": settings.CELERY_EXECUTE_QUEUE},
        "app.tasks.periodic.*": {"queue": settings.CELERY_PERIODIC_QUEUE},
    },
    task_create_missing_queues=True,
    # 研究任务耗时较长，放宽超时
    task_soft_time_limit=600,
    task_time_limit=900,
    # Redis broker 消息可见性超时：Worker 崩溃后未 ACK 的消息多久后重新可见
    broker_transport_options={
        "visibility_timeout": settings.CELERY_VISIBILITY_TIMEOUT,
    },
    # Beat 定时调度：数据 TTL 清理 + 周期 Recovery Scanner
    beat_schedule={
        "cleanup_old_research_tasks": {
            "task": "app.tasks.periodic.cleanup_old_research_tasks",
            "schedule": 86400.0,  # 每天执行一次
            "kwargs": {
                "max_age_days": getattr(settings, "CLEANUP_TASK_MAX_AGE_DAYS", 30),
            },
        },
        "recover_expired_research_tasks": {
            "task": "app.tasks.periodic.recover_expired_research_tasks",
            "schedule": settings.RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS,
        },
    },
    beat_max_loop_interval=300,
)

# Windows: solo 池（默认），避免 eventlet/gevent 与 asyncio 冲突
if sys.platform == "win32":
    celery_app.conf.update(
        worker_pool="solo",
    )

# 注册任务模块（导入即注册 @celery_app.task 装饰的任务）
import app.tasks.periodic  # noqa: E402, F401


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """Worker 启动完成时触发恢复检查。

    与 API 启动、周期 Beat、手动治理调用同一恢复服务
    （app.tasks.recovery.recover_stale_tasks，纯 DB lease，不依赖 Redis），
    实现不依赖 Redis visibility_timeout 的快速恢复。
    """
    logger.info("Celery Worker 已就绪，触发过时任务恢复检查")
    try:
        from app.tasks.event_loop import get_worker_loop
        from app.tasks.recovery import recover_stale_tasks

        loop = get_worker_loop()
        recovered = loop.run_until_complete(recover_stale_tasks())
        if recovered:
            logger.warning("Worker 就绪恢复：已重新投递 %d 个任务: %s", len(recovered), recovered)
    except Exception:
        logger.exception("Worker 就绪恢复检查失败")
