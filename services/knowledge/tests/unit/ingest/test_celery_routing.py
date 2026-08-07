"""Knowledge Celery 任务路由契约测试。"""

import pytest
from app.ingest.celery_app import celery_app


def _matches_any_route(task_name: str, routes: dict[str, object]) -> bool:
    """任务名命中任一 task_routes 键（支持 ``*`` 通配后缀）。"""
    for pattern in routes:
        if pattern.endswith("*"):
            if task_name.startswith(pattern[:-1]):
                return True
        elif task_name == pattern:
            return True
    return False


@pytest.mark.parametrize(
    ("task_name", "expected_queue"),
    [
        ("app.ingest.tasks.ingest_document", "knowledge.ingest"),
        ("app.ingest.recovery_tasks.scan_stuck_versions", "knowledge.ingest"),
        ("app.ingest.delete_tasks.delete_document", "knowledge.delete"),
        ("app.ingest.delete_tasks.delete_kb", "knowledge.delete"),
    ],
)
def test_knowledge任务投递到worker监听的命名队列(task_name, expected_queue):
    """防止任务落入 worker 不监听的默认 celery 队列。"""
    route = celery_app.amqp.router.route({}, task_name, args=(1,), kwargs={})

    assert route["queue"].name == expected_queue


def test_every_business_task_is_routed():
    """守卫：任何新增业务任务必须显式路由，禁止静默落入默认 ``celery`` 队列。

    本次修复的同类 Bug —— “任务未路由 → 落入 worker 不监听的默认队列 → 永不处理”——
    会在此处暴露：新增业务任务若漏配 task_routes，本测试立即失败。
    """
    routes = celery_app.conf.task_routes
    unmapped = [
        name
        for name in celery_app.tasks
        if not name.startswith("celery.") and not _matches_any_route(name, routes)
    ]
    assert unmapped == [], f"以下业务任务未被 task_routes 覆盖: {unmapped}"
