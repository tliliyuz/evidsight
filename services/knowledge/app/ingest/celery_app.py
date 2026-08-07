"""Celery 应用配置 — broker/backend 从 settings 读取"""

import asyncio
import sys

from celery import Celery

# Worker 启动时初始化 ChromaDB（独立进程，不走 FastAPI lifespan）
from celery.signals import worker_process_init

from app.config import settings
from app.core.chroma_client import init_chroma

# Windows 下 aiomysql 需要 SelectorEventLoop，Proactor 会卡死
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

celery_app = Celery(
    "docmind",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "app.ingest.tasks.ingest_document": {"queue": settings.CELERY_INGEST_QUEUE},
        "app.ingest.tasks.ingest_version": {"queue": settings.CELERY_INGEST_QUEUE},
        "app.ingest.recovery_tasks.scan_stuck_versions": {"queue": settings.CELERY_INGEST_QUEUE},
        "app.ingest.delete_tasks.delete_document": {"queue": settings.CELERY_DELETE_QUEUE},
        "app.ingest.delete_tasks.delete_kb": {"queue": settings.CELERY_DELETE_QUEUE},
    },
    task_create_missing_queues=True,
    # 入库任务耗时较长，放宽超时
    task_soft_time_limit=600,
    task_time_limit=900,
    # 版本恢复扫描（ADR-007）：每 60s 检查卡死版本/卡死 KB 发布锁
    beat_schedule={
        "scan-stuck-versions": {
            "task": "app.ingest.recovery_tasks.scan_stuck_versions",
            "schedule": 60.0,
        },
    },
)

# Windows: solo 池（默认），避免 eventlet/gevent 与 asyncio 冲突
if sys.platform == "win32":
    celery_app.conf.update(
        worker_pool="solo",
    )


@worker_process_init.connect
def _init_worker_resources(**kwargs):
    init_chroma()


# 注册任务模块（导入即注册 @celery_app.task 装饰的任务）
import app.ingest.delete_tasks  # noqa: E402, F401
import app.ingest.recovery_tasks  # noqa: E402, F401
import app.ingest.tasks  # noqa: E402, F401
