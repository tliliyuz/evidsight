"""就绪探针测试 — /api/health/ready（对齐 ADR-005 readiness）

liveness（/api/health）只验证进程活着；readiness 做关键依赖检查，
Service 公钥不可加载时返回 503，避免带病对外服务。
"""

import json

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_ready_公钥可加载_返回200(monkeypatch, tmp_path):
    keys_file = tmp_path / "public_keys.json"
    keys_file.write_text(json.dumps({"kid": "PEM"}), encoding="utf-8")
    monkeypatch.setattr(
        settings,
        "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
        str(keys_file),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_公钥不可加载_返回503(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings,
        "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
        str(tmp_path / "missing.json"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
