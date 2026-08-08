"""Research v1 canonical SSE 投影验收测试。"""

import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("granular", "canonical"),
    [
        ("task.status.snapshot", "snapshot"),
        ("task.progress", "task.updated"),
        ("task.completed", "task.updated"),
        ("phase.started", "phase.updated"),
        ("phase.completed", "phase.updated"),
        ("step.progress", "step.updated"),
        ("checkpoint.saved", "step.updated"),
        ("agent.action", "step.updated"),
        ("agent.observation", "step.updated"),
    ],
)
def test_granular事件投影为canonical且保留持久游标(granular, canonical):
    from app.api.research_common import canonicalize_sse_chunk

    chunk = f"id: 7\nevent: {granular}\ndata: {json.dumps({'value': 1})}\n\n"

    projected = canonicalize_sse_chunk(chunk)

    assert "id: 7" in projected
    assert f"event: {canonical}" in projected
    assert granular not in projected


def test_旧路由仍保留granular事件名():
    """兼容层不应被 v1 canonical 投影反向改写。"""
    from app.api.research_common import canonicalize_sse_chunk

    chunk = 'event: step.started\ndata: {"step_id":"s1"}\n\n'
    assert "event: step.started" in chunk
    assert "event: step.updated" in canonicalize_sse_chunk(chunk)


@pytest.mark.asyncio
async def test_v1终态响应发送canonical快照与stream_end():
    from app.api.research_common import build_task_events_response

    response = build_task_events_response(
        SimpleNamespace(headers={}),
        SimpleNamespace(status="completed"),
        None,
        {"task_id": "t1", "status": "completed"},
        canonical=True,
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: snapshot" in body
    assert "event: stream.end" in body
    assert "task.status.snapshot" not in body


@pytest.mark.asyncio
async def test_旧终态响应仍只发送granular快照():
    from app.api.research_common import build_task_events_response

    response = build_task_events_response(
        SimpleNamespace(headers={}),
        SimpleNamespace(status="completed"),
        None,
        {"task_id": "t1", "status": "completed"},
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: task.status.snapshot" in body
    assert "event: stream.end" not in body
