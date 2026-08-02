"""Celery 队列路由配置测试。"""

from app.config import settings
from app.tasks.celery_app import celery_app


def test_research_tasks_are_routed_to_worker_queues():
    """所有 Research 任务必须投递到 Worker 实际监听的显式队列。

    契约断言：默认/路由队列必须是命名空间队列（禁止默认 ``celery``）；
    同时绑定 settings，避免“代码与配置自洽但测试硬编码”的假阳性。
    """
    assert celery_app.conf.task_default_queue == settings.CELERY_EXECUTE_QUEUE
    assert celery_app.conf.task_default_queue == "research.execute"
    assert celery_app.conf.task_routes == {
        "execute_research_task": {"queue": settings.CELERY_EXECUTE_QUEUE},
        "app.tasks.periodic.*": {"queue": settings.CELERY_PERIODIC_QUEUE},
    }
    assert celery_app.conf.task_routes["execute_research_task"]["queue"] == "research.execute"
    assert celery_app.conf.task_routes["app.tasks.periodic.*"]["queue"] == "research.periodic"
