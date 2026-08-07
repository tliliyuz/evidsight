"""POST /api/v1/research/tasks — 幂等创建验收（对齐 API.md §8.1 / §8.2）。

SDD 门禁：RED —— 目标行为（v1 幂等创建端点、Idempotency-Key、重放与 409）当前缺失。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.research_task import ResearchTask
from app.models.research_task_knowledge_base import ResearchTaskKnowledgeBase

KB_A = "11111111-1111-4111-8111-111111111111"
KB_B = "22222222-2222-4222-8222-222222222222"
IDEM_KEY = "req-key-0001"


def _payload(topic="量子计算对密码学的影响", strategy="knowledge", kbs=(KB_A,)):
    body = {
        "topic": topic,
        "requirements": {"task_type": "analysis", "depth": "quick"},
        "source_strategy": strategy,
    }
    if strategy != "web":
        body["knowledge_base_ids"] = list(kbs)
    return body


def _headers(auth_headers: dict, key: str = IDEM_KEY) -> dict:
    return {**auth_headers, "Idempotency-Key": key}


class TestResearchV1Create:
    """POST /api/v1/research/tasks"""

    async def test_缺少IdempotencyKey_返回422(self, async_client: AsyncClient, auth_headers: dict):
        r = await async_client.post("/api/v1/research/tasks", json=_payload(), headers=auth_headers)
        assert r.status_code == 422
        assert r.json()["code"] == "E9003"

    async def test_正常创建_返回202且replayed_false(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        with patch("app.api.research_v1._execute_research_task.delay") as mock_delay:
            r = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers)
            )
        assert r.status_code == 202
        data = r.json()["data"]
        assert data["idempotent_replayed"] is False
        assert len(data["task_id"]) == 36
        assert data["status"] == "pending"
        mock_delay.assert_called_once()

    async def test_同Key同载荷_重放同一task且replayed_true(
        self, async_client: AsyncClient, auth_headers: dict, db_session
    ):
        with patch("app.api.research_v1._execute_research_task.delay"):
            r1 = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers)
            )
            r2 = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers)
            )
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["data"]["task_id"] == r2.json()["data"]["task_id"]
        assert r1.json()["data"]["idempotent_replayed"] is False
        assert r2.json()["data"]["idempotent_replayed"] is True

        stmt = select(ResearchTask).where(
            ResearchTask.idempotency_key == IDEM_KEY,
            ResearchTask.user_id == "550e8400-e29b-41d4-a716-446655440000",
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 1

    async def test_同Key不同载荷_返回409E2009(self, async_client: AsyncClient, auth_headers: dict):
        with patch("app.api.research_v1._execute_research_task.delay"):
            r1 = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers)
            )
            r2 = await async_client.post(
                "/api/v1/research/tasks",
                json=_payload(topic="完全不同的研究主题"),
                headers=_headers(auth_headers),
            )
        assert r1.status_code == 202
        assert r2.status_code == 409
        assert r2.json()["code"] == "E2009"

    async def test_同Key不同用户_各自创建(self, async_client: AsyncClient, auth_headers: dict):
        from jose import jwt as jose_jwt

        from app.config import settings

        now = datetime.now(timezone.utc)
        other_token = jose_jwt.encode(
            {
                "iss": settings.EVIDSIGHT_PLATFORM_JWT_ISSUER,
                "aud": ["evidsight-knowledge", settings.EVIDSIGHT_RESEARCH_JWT_AUDIENCE],
                "sub": "99999999-9999-4999-8999-999999999999",
                "username": "other",
                "role": "user",
                "token_type": "access",
                "jti": "research-test-other",
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(minutes=15),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        other_headers = {"Authorization": f"Bearer {other_token}", "Idempotency-Key": IDEM_KEY}
        with patch("app.api.research_v1._execute_research_task.delay"):
            r1 = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers)
            )
            r2 = await async_client.post(
                "/api/v1/research/tasks", json=_payload(), headers=other_headers
            )
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["data"]["task_id"] != r2.json()["data"]["task_id"]

    async def test_knowledge策略_持久化KB选择行(
        self, async_client: AsyncClient, auth_headers: dict, db_session
    ):
        with patch("app.api.research_v1._execute_research_task.delay"):
            r = await async_client.post(
                "/api/v1/research/tasks",
                json=_payload(kbs=(KB_B, KB_A)),
                headers=_headers(auth_headers),
            )
        assert r.status_code == 202
        task_id = r.json()["data"]["task_id"]
        stmt = (
            select(ResearchTaskKnowledgeBase)
            .where(ResearchTaskKnowledgeBase.task_id == task_id)
            .order_by(ResearchTaskKnowledgeBase.selection_order)
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        assert [(x.knowledge_base_id, x.selection_order) for x in rows] == [(KB_B, 0), (KB_A, 1)]

    async def test_web策略带KB_返回422(self, async_client: AsyncClient, auth_headers: dict):
        r = await async_client.post(
            "/api/v1/research/tasks",
            json={
                "topic": "web主题",
                "requirements": {"task_type": "analysis"},
                "source_strategy": "web",
                "knowledge_base_ids": [KB_A],
            },
            headers=_headers(auth_headers),
        )
        assert r.status_code == 422

    async def test_IdempotencyKey超长_返回422(self, async_client: AsyncClient, auth_headers: dict):
        r = await async_client.post(
            "/api/v1/research/tasks", json=_payload(), headers=_headers(auth_headers, key="k" * 129)
        )
        assert r.status_code == 422
        assert r.json()["code"] == "E9003"

    async def test_未认证_返回401(self, async_client: AsyncClient):
        r = await async_client.post(
            "/api/v1/research/tasks", json=_payload(), headers={"Idempotency-Key": IDEM_KEY}
        )
        assert r.status_code == 401
