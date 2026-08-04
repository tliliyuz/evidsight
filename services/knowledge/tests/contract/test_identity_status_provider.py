"""Internal Identity Status 契约 — Knowledge 作为 Provider 的验收测试。

对齐 API.md §11.1、contracts/README.md §5.1。SDD 门禁：
GREEN 目标：端点返回 200 + IdentityStatusResponse；错误路径返回契约错误信封。
错误信封通过 error-response.schema.json 校验。
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.config import settings
from app.core.uuid_helpers import validate_uuid_format
from evidsight_contracts.loader import validator_for


def _make_service_keypair(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    keys_file = tmp_path / "public_keys.json"
    keys_file.write_text(json.dumps({"test-kid": public_pem}), encoding="utf-8")
    return private_pem


def _service_token(private_pem) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER,
        "aud": settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE,
        "sub": "research-service",
        "token_type": "service",
        "jti": "contract-test-jti",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=60),
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "test-kid"})


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-EvidSight-Contract-Version": "1.0.0",
        "X-Request-ID": "test-request-id",
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }


@pytest.fixture
def service_auth(tmp_path, monkeypatch):
    private_pem = _make_service_keypair(tmp_path)
    monkeypatch.setattr(
        settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
        str(tmp_path / "public_keys.json"),
    )
    return private_pem


class TestIdentityStatusProvider:
    PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"

    def test_provider_can_produce_schema_compliant_response(self):
        response = {
            "contract_version": "1.0.0",
            "platform_user_id": self.PLATFORM_UUID,
            "status": "active",
            "status_version": 1,
        }
        errors = list(validator_for("identity-status-response").iter_errors(response))
        assert not errors, f"Provider 构造的响应不符合契约:\n{errors}"

    def test_platform_uuid_is_valid_v4(self):
        assert validate_uuid_format(self.PLATFORM_UUID)

    @pytest.mark.asyncio
    async def test_active_user_returns_200_schema_compliant(self, async_client, mock_db, service_auth):
        """GREEN：active 用户 → 200 + IdentityStatusResponse，且不含用户资料字段。"""
        from app.models.user import User
        user = User(
            id=1, platform_user_id=self.PLATFORM_UUID,
            username="u", password_hash="x", role="user", status="active",
            status_version=1,
        )
        result = AsyncMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        mock_db.execute = AsyncMock(return_value=result)

        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        errors = list(validator_for("identity-status-response").iter_errors(body))
        assert not errors, f"响应不符合契约:\n{errors}"
        assert "username" not in body and "role" not in body

    @pytest.mark.asyncio
    async def test_missing_service_auth_returns_401(self, async_client, service_auth):
        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=_headers(""),
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_SERVICE_UNAUTHENTICATED"
        errors = list(validator_for("error-response").iter_errors(body))
        assert not errors, f"错误响应不符合契约:\n{errors}"

    @pytest.mark.asyncio
    async def test_unsupported_contract_version_returns_400(self, async_client, service_auth):
        headers = _headers(_service_token(service_auth))
        headers["X-EvidSight-Contract-Version"] = "2.0.0"
        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status", headers=headers
        )
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_400(self, async_client, service_auth):
        response = await async_client.get(
            "/internal/v1/identity/users/not-a-uuid/status",
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_disabled_user_returns_403(self, async_client, mock_db, service_auth):
        from app.models.user import User
        user = User(
            id=1, platform_user_id=self.PLATFORM_UUID,
            username="u", password_hash="x", role="user", status="disabled",
            status_version=2,
        )
        result = AsyncMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        mock_db.execute = AsyncMock(return_value=result)

        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"

    @pytest.mark.asyncio
    async def test_missing_user_returns_403(self, async_client, mock_db, service_auth):
        result = AsyncMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=result)

        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"

    @pytest.mark.asyncio
    async def test_db_unavailable_returns_503(self, async_client, mock_db, service_auth):
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_IDENTITY_UNAVAILABLE"
        assert body["error"]["retryable"] is True
