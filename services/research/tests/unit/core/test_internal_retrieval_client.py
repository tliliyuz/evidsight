"""Internal Retrieval Consumer 客户端单测 — mock httpx，不发起真实 HTTP。

对齐 contracts/README.md §6-7/§10 与 RESEARCH_PIPELINE.md §6.1/§12：
- 请求必须携带 Service JWT、Contract 版本、X-Request-ID、traceparent；
- 200 → 按契约解析并校验（returned_count == len(results)、稳定 ID 齐全）；
- 403 KB_FORBIDDEN → InternalKnowledgeForbiddenException（E3115，fail-closed）；
- 403 AUTH_USER_DISABLED → UserDisabledException（E1010）；
- 503 INTERNAL_RETRIEVAL_UNAVAILABLE / 限流 / 网络 / 超时 → 可重试 E3116，重试耗尽后抛出；
- 400 INTERNAL_CONTRACT_UNSUPPORTED/INVALID → 契约错误 E3117，fail-closed 不重试。

SDD 门禁：RED —— 目标行为（Internal Retrieval Consumer）当前缺失。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.core import internal_retrieval_client
from app.core.exceptions import (
    InternalKnowledgeForbiddenException,
    InternalRetrievalContractException,
    InternalRetrievalUnavailableException,
    UserDisabledException,
)

PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"
KB_UUID = "550e8400-e29b-41d4-a716-446655440010"
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


def _ok_hit(hit_id: str = "550e8400-e29b-41d4-a716-446655440100") -> dict:
    return {
        "hit_id": hit_id,
        "knowledge_base_id": KB_UUID,
        "document_id": "550e8400-e29b-41d4-a716-446655440020",
        "document_version_id": "550e8400-e29b-41d4-a716-446655440031",
        "segment_id": "550e8400-e29b-41d4-a716-446655440041",
        "document_display_name": "权限设计文档",
        "section_title": "权限矩阵",
        "location": {"page_number": 3},
        "minimal_excerpt": "KB 的 READ 权限决定该用户是否可检索。",
        "scores": [{"score_kind": "vector", "value": 0.87, "rank": 0}],
        "source_updated_at": "2026-08-03T09:00:00Z",
        "retrieved_at": "2026-08-04T12:00:00Z",
        "access_scope": "internal",
    }


def _ok_response(hits: list[dict], has_more: bool = False) -> dict:
    return {
        "contract_version": "1.0.0",
        "request_id": "req-1",
        "results": hits,
        "returned_count": len(hits),
        "has_more": has_more,
    }


def _client_ctx(mock_post):
    """构造 async with httpx.AsyncClient() 的 mock 上下文。"""
    client = AsyncMock()
    client.post = mock_post
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestInternalRetrievalClient:
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
        monkeypatch.setattr(settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE", str(priv_file))
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS", 60)
        monkeypatch.setattr(settings, "EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL", BASE_URL)
        monkeypatch.setattr(settings, "EVIDSIGHT_INTERNAL_RETRIEVAL_TIMEOUT_SECONDS", 5)
        monkeypatch.setattr(settings, "EVIDSIGHT_INTERNAL_RETRIEVAL_RETRY_MAX", 2)

    async def test_200_解析命中并校验请求头与载荷(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _ok_response([_ok_hit()])
        mock_post = AsyncMock(return_value=mock_resp)

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(mock_post),
        ) as mock_cls:
            result = await internal_retrieval_client.search_retrieval(
                user_id=PLATFORM_UUID,
                knowledge_base_ids=[KB_UUID],
                query="权限矩阵如何判定 READ",
            )

        assert len(result.results) == 1
        hit = result.results[0]
        assert hit.document_id == "550e8400-e29b-41d4-a716-446655440020"
        assert hit.minimal_excerpt  # 仅在当前 Step 内存中可用
        assert result.returned_count == 1

        # 客户端构造：URL、超时与请求头
        _client_kwargs = mock_cls.call_args.kwargs
        assert _client_kwargs["timeout"] == 5
        args, kwargs = mock_post.call_args
        assert args[0] == f"{BASE_URL}/internal/v1/retrieval/search"
        headers = kwargs["headers"]
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["X-EvidSight-Contract-Version"] == "1.0.0"
        assert headers["X-Request-ID"]
        assert headers["traceparent"].startswith("00-")
        # 请求体只含契约字段，不带角色/授权结论
        body = kwargs["json"]
        assert body["contract_version"] == "1.0.0"
        assert body["user_id"] == PLATFORM_UUID
        assert body["knowledge_base_ids"] == [KB_UUID]
        assert body["purpose"] == "research_retrieval"
        assert body["query"] == "权限矩阵如何判定 READ"
        assert "role" not in body and "owner" not in body and "authorized" not in body

    async def test_200_多KB多命中(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _ok_response(
            [_ok_hit("550e8400-e29b-41d4-a716-446655440100"),
             _ok_hit("550e8400-e29b-41d4-a716-446655440101")],
            has_more=True,
        )

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            result = await internal_retrieval_client.search_retrieval(
                user_id=PLATFORM_UUID,
                knowledge_base_ids=[KB_UUID, "550e8400-e29b-41d4-a716-446655440011"],
                query="多 KB 检索",
            )

        assert len(result.results) == 2
        assert result.has_more is True

    async def test_returned_count与results长度不一致_抛契约错误(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        bad = _ok_response([_ok_hit()])
        bad["returned_count"] = 5  # 与 len(results)=1 不一致
        mock_resp.json.return_value = bad

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(InternalRetrievalContractException):
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

    async def test_命中缺少稳定ID_抛契约错误(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        hit = _ok_hit()
        del hit["segment_id"]  # 命中必须含完整稳定身份
        mock_resp.json.return_value = _ok_response([hit])

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(InternalRetrievalContractException):
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

    async def test_403_KB_FORBIDDEN_抛fail_closed不重试(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = _error_json("KB_FORBIDDEN")

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ) as mock_cls:
            with pytest.raises(InternalKnowledgeForbiddenException) as exc:
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

        assert exc.value.error_code == "E3115"
        assert exc.value.status_code == 403
        assert not exc.value.error_detail.get("recoverable")
        # KB_FORBIDDEN 不重试：只发一次请求
        assert mock_cls.return_value.__aenter__.return_value.post.await_count == 1

    async def test_403_AUTH_USER_DISABLED_抛UserDisabled(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = _error_json("AUTH_USER_DISABLED")

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(UserDisabledException) as exc:
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

        assert exc.value.error_code == "E1010"

    async def test_400_契约不支持_抛契约错误不重试(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = _error_json("INTERNAL_CONTRACT_UNSUPPORTED")

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ) as mock_cls:
            with pytest.raises(InternalRetrievalContractException) as exc:
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

        assert exc.value.error_code == "E3117"
        assert not exc.value.error_detail.get("recoverable")
        assert mock_cls.return_value.__aenter__.return_value.post.await_count == 1

    async def test_503_瞬时不可用_重试耗尽后抛E3116(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = _error_json("INTERNAL_RETRIEVAL_UNAVAILABLE", retryable=True)

        mock_post = AsyncMock(return_value=mock_resp)
        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(mock_post),
        ):
            with pytest.raises(InternalRetrievalUnavailableException) as exc:
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

        assert exc.value.error_code == "E3116"
        assert exc.value.error_detail.get("recoverable") is True
        # 重试上限 2：共 3 次请求
        assert mock_post.await_count == 3

    async def test_网络错误_重试耗尽后抛E3116(self):
        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(side_effect=ConnectionError("knowledge down"))),
        ):
            with pytest.raises(InternalRetrievalUnavailableException):
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )

    async def test_超时_重试耗尽后抛E3116(self):
        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(side_effect=TimeoutError("timeout"))),
        ):
            with pytest.raises(InternalRetrievalUnavailableException):
                await internal_retrieval_client.search_retrieval(
                    user_id=PLATFORM_UUID, knowledge_base_ids=[KB_UUID], query="q"
                )


class TestInternalResolveClient:
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
        monkeypatch.setattr(settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE", str(priv_file))
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS", 60)
        monkeypatch.setattr(settings, "EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL", BASE_URL)
        monkeypatch.setattr(settings, "EVIDSIGHT_INTERNAL_RETRIEVAL_TIMEOUT_SECONDS", 5)
        monkeypatch.setattr(settings, "EVIDSIGHT_INTERNAL_RETRIEVAL_RETRY_MAX", 2)

    def _reference(self) -> dict:
        return {
            "knowledge_base_id": KB_UUID,
            "document_id": "550e8400-e29b-41d4-a716-446655440020",
            "document_version_id": "550e8400-e29b-41d4-a716-446655440031",
            "segment_id": "550e8400-e29b-41d4-a716-446655440041",
        }

    async def test_resolve_构造请求并解析(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "contract_version": "1.0.0",
            "request_id": "req-r",
            "resolved": [
                {
                    "source_identity": self._reference(),
                    "minimal_excerpt": "可见性优先于所有权参与 READ 判定。",
                    "location": {"page_number": 4},
                    "source_updated_at": "2026-08-03T09:00:00Z",
                }
            ],
            "resolved_count": 1,
        }
        mock_post = AsyncMock(return_value=mock_resp)

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(mock_post),
        ):
            result = await internal_retrieval_client.resolve_retrieval(
                user_id=PLATFORM_UUID, references=[self._reference()]
            )

        assert len(result) == 1
        args, kwargs = mock_post.call_args
        assert args[0] == f"{BASE_URL}/internal/v1/retrieval/resolve"
        body = kwargs["json"]
        assert body["purpose"] == "research_evidence_resolve"
        assert body["references"] == [self._reference()]
        assert body["contract_version"] == "1.0.0"

    async def test_resolve_EVIDENCE_SOURCE_UNAVAILABLE_契约错误(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = _error_json("EVIDENCE_SOURCE_UNAVAILABLE")

        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(return_value=mock_resp)),
        ):
            with pytest.raises(InternalRetrievalContractException):
                await internal_retrieval_client.resolve_retrieval(
                    user_id=PLATFORM_UUID, references=[self._reference()]
                )

    async def test_resolve_网络错误_重试耗尽后抛E3116(self):
        with patch(
            "app.core.internal_retrieval_client.httpx.AsyncClient",
            return_value=_client_ctx(AsyncMock(side_effect=ConnectionError("down"))),
        ):
            with pytest.raises(InternalRetrievalUnavailableException):
                await internal_retrieval_client.resolve_retrieval(
                    user_id=PLATFORM_UUID, references=[self._reference()]
                )
