"""Celery 队列路由配置测试。"""

from app.tasks.celery_app import celery_app


def test_research_tasks_are_routed_to_worker_queues():
    """所有 Research 任务必须投递到 Worker 实际监听的显式队列。"""
    assert celery_app.conf.task_default_queue == "research.execute"
    assert celery_app.conf.task_routes == {
        "execute_research_task": {"queue": "research.execute"},
        "app.tasks.periodic.*": {"queue": "research.periodic"},
    }
