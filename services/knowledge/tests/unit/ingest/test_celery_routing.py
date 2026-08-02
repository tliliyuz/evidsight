"""Knowledge Celery 任务路由契约测试。"""

import pytest

from app.ingest.celery_app import celery_app


@pytest.mark.parametrize(
    ("task_name", "expected_queue"),
    [
        ("app.ingest.tasks.ingest_document", "knowledge.ingest"),
        ("app.ingest.delete_tasks.delete_document", "knowledge.delete"),
        ("app.ingest.delete_tasks.delete_kb", "knowledge.delete"),
    ],
)
def test_knowledge任务投递到worker监听的命名队列(task_name, expected_queue):
    """防止任务落入 worker 不监听的默认 celery 队列。"""
    route = celery_app.amqp.router.route({}, task_name, args=(1,), kwargs={})

    assert route["queue"].name == expected_queue
