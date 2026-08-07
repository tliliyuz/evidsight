"""Identity Status Client 单测 — mock httpx，不发起真实 HTTP。

对齐 API.md §11.1 与 TESTING.md IA-012 身份状态契约：
- 请求必须携带 Service JWT、Contract 版本、X-Request-ID、traceparent；
- 200 → 放行；403 AUTH_USER_DISABLED → UserDisabledException（E1010）；
- 503 INTERNAL_IDENTITY_UNAVAILABLE / 网络 / 超时 → ServiceUnavailableException（E9002），失败关闭。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.core import identity_status_client
from app.core.exceptions import ServiceUnavailableException, UserDisabledException

PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"
BASE_URL = "http://knowledge-api:8000"


def _error_json(code: str, retryable: bool = False) -> dict:
    return {
        "error": {
            "error_code": code,
            "message": code,
            "request_id": "test-rid",
            "retryable": retryable,
            "details": {},
        }
    }


def _client_ctx(mock_get):
    """构造 async with httpx.AsyncClient() 的 mock 上下文。"""
    client = AsyncMock()
    client.get = mock_get
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestIdentityStatusClient:
    @pytest.fixture(autouse=True)
    def _cfg(self, tmp_path, monkeypatch):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        priv_file = tmp_path / "private.pem"
        priv_file.write_text(private_pem, encoding="utf-8")

        monkeypatch.setattr(settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_ACTIVE_KID", "test-kid")
        monkeypatch.setattr(
            settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE", str(priv_file)
        )
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS", 60)
        monkeypatch.setattr(settings, "EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL", BASE_URL)
        monkeypatch.setattr(settings, "EVIDSIGHT_IDENTITY_STATUS_TIMEOUT_SECONDS", 5)

    async def test_200_放行并校验请求头(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "contract_version": "1.0.0",
            "platform_user_id": PLATFORM_UUID,
            "status": "active",
            "status_version": 1,
        }
        mock_get = AsyncMock(return_value=mock_resp)

        with patch(
            "app.core.identity_status_client.httpx.AsyncClient", return_value=_client_ctx(mock_get)
        ) as mock_cls:
            await identity_status_client.check_user_status(PLATFORM_UUID)

        # AsyncClient(timeout=5) 构造
        _client_kwargs = mock_cls.call_args.kwargs
        assert _client_kwargs["timeout"] == 5
        # GET 请求 URL 与头部
        args, kwargs = mock_get.call_args
        assert args[0] == f"{BASE_URL}/internal/v1/identity/users/{PLATFORM_UUID}/status"
        headers = kwargs["headers"]
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["X-EvidSight-Contract-Version"] == "1.0.0"
        assert headers["X-Request-ID"]
        assert headers["traceparent"].startswith("00-")

    async def test_403_AUTH_USER_DISABLED_抛UserDisabledException(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = _error_json("AUTH_USER_DISABLED")

        with patch(
            "app.core.identity_status_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(UserDisabledException) as exc:
                await identity_status_client.check_user_status(PLATFORM_UUID)

        assert exc.value.error_code == "E1010"
        assert exc.value.status_code == 401

    async def test_503_INTERNAL_IDENTITY_UNAVAILABLE_抛ServiceUnavailable(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = _error_json("INTERNAL_IDENTITY_UNAVAILABLE", retryable=True)

        with patch(
            "app.core.identity_status_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(ServiceUnavailableException) as exc:
                await identity_status_client.check_user_status(PLATFORM_UUID)

        assert exc.value.error_code == "E9002"
        assert exc.value.status_code == 503

    async def test_网络错误_失败关闭(self):
        with patch(
            "app.core.identity_status_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(side_effect=ConnectionError("knowledge down"))),
        ):
            with pytest.raises(ServiceUnavailableException):
                await identity_status_client.check_user_status(PLATFORM_UUID)

    async def test_超时_失败关闭(self):
        with patch(
            "app.core.identity_status_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(side_effect=TimeoutError("timeout"))),
        ):
            with pytest.raises(ServiceUnavailableException):
                await identity_status_client.check_user_status(PLATFORM_UUID)

    async def test_意外非2xx_失败关闭(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = _error_json("INTERNAL_SERVER_ERROR")

        with patch(
            "app.core.identity_status_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(ServiceUnavailableException):
                await identity_status_client.check_user_status(PLATFORM_UUID)
