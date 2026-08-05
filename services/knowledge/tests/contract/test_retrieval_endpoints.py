"""Internal Retrieval 与 Evidence Resolve — Knowledge 作为 Provider 的端点级验收测试。

对齐 API.md §11.2、RAG_PIPELINE.md §7、contracts/README.md §3。SDD 门禁：
GREEN 目标：/internal/v1/retrieval/search 与 /resolve 按固定处理顺序
（Research 服务身份 → Contract 版本与结构 → 用户 active → 逐 KB READ → 检索/解析）
返回契约响应；任一步失败返回 error-response.schema.json 信封，不泄露 ORM/路径/缓存。

本文件通过 FakeSession 按查询目标实体 + uuid 等值过滤路由预置行，屏蔽真实 MySQL；
检索执行函数 _retrieve_kb 在成功路径被 monkeypatch，屏蔽 ChromaDB/Embedding/BM25。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from evidsight_contracts.loader import validator_for

# ---------------- 测试常量 ----------------

USER = "550e8400-e29b-41d4-a716-446655440001"
ADMIN = "550e8400-e29b-41d4-a716-446655440002"
KB_A = "550e8400-e29b-41d4-a716-446655440010"       # public，owner=user2，USER 可读
KB_PRIVATE = "550e8400-e29b-41d4-a716-446655440011"  # private，owner=user1，USER 可读
KB_OTHER = "550e8400-e29b-41d4-a716-446655440012"    # private，owner=user2，USER 不可读
DOC_A = "550e8400-e29b-41d4-a716-446655440020"
VER_A1 = "550e8400-e29b-41d4-a716-446655440031"
SEG_A1 = "550e8400-e29b-41d4-a716-446655440041"
SEG_A2 = "550e8400-e29b-41d4-a716-446655440042"
HIT_ID = "550e8400-e29b-41d4-a716-446655440100"


# ---------------- Service JWT / HTTP 辅助 ----------------

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


def _search_body(**overrides) -> dict:
    body = {
        "contract_version": "1.0.0",
        "user_id": USER,
        "knowledge_base_ids": [KB_A],
        "query": "权限设计",
        "purpose": "research_retrieval",
    }
    body.update(overrides)
    return body


def _resolve_body(references=None, **overrides) -> dict:
    body = {
        "contract_version": "1.0.0",
        "user_id": USER,
        "references": references or [
            {
                "knowledge_base_id": KB_A,
                "document_id": DOC_A,
                "document_version_id": VER_A1,
                "segment_id": SEG_A1,
            }
        ],
        "purpose": "research_evidence_resolve",
    }
    body.update(overrides)
    return body


@pytest.fixture
def service_auth(tmp_path, monkeypatch):
    private_pem = _make_service_keypair(tmp_path)
    monkeypatch.setattr(
        settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
        str(tmp_path / "public_keys.json"),
    )
    return private_pem


# ---------------- FakeSession：按实体 + uuid 等值过滤路由预置行 ----------------

def _extract_equality_filters(query) -> dict:
    """从 select 的 where 条件提取 str 等值过滤（column.key -> value）。

    SQLAlchemy 2.0 中 `Column == literal` 右侧是 BindParameter，需解包取 value。
    只处理简单 `Column == literal_str`；in_/int 等值等条件不提取（返回全部预置行，
    由 service 自行过滤）。对齐 FakeSession 只服务测试的目标：User/KB/Document/
    DocumentVersion 均以 uuid 等值定位。
    """
    from sqlalchemy.sql.elements import BindParameter

    filters: dict[str, str] = {}
    criteria = getattr(query, "_where_criteria", None)
    if not criteria:
        return filters
    for crit in criteria:
        left = getattr(crit, "left", None)
        right = getattr(crit, "right", None)
        if isinstance(right, BindParameter):
            right = right.value
        if left is not None and right is not None and isinstance(right, str):
            key = getattr(left, "key", None)
            if key:
                filters[key] = right
    return filters


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalars(self):
        return self


class FakeSession:
    """模拟 async DB session：execute 按目标实体返回预置行，再按 uuid 等值过滤。"""

    def __init__(self):
        self._rows_by_entity: dict = {}

    def seed(self, entity, rows):
        self._rows_by_entity[entity] = list(rows) if isinstance(rows, list) else [rows]

    async def execute(self, query, *args, **kwargs):
        descriptions = getattr(query, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        rows = self._rows_by_entity.get(entity, [])
        filters = _extract_equality_filters(query)
        if filters:
            rows = [
                r for r in rows
                if all(getattr(r, key, None) == value for key, value in filters.items())
            ]
        return FakeResult(rows)

    async def refresh(self, instance):
        """模拟 session.refresh：默认不改变实例。

        _require_kb_ready 在 index_status=='updating' 时轮询 refresh；测试可
        覆盖本方法模拟发布锁收敛（index_status: updating → ready）。
        """
        return None


@pytest.fixture
def fake_db():
    return FakeSession()


@pytest.fixture
async def contract_client(fake_db):
    app.dependency_overrides[get_db] = lambda: fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------- ORM 预置行构造 ----------------

def _user(**overrides):

    base = {
        "id": 1, "platform_user_id": USER, "username": "u", "password_hash": "x",
        "role": "user", "status": "active", "status_version": 1,
    }
    base.update(overrides)
    return User(**base)


def _kb(**overrides):

    base = {
        "id": 10, "uuid": KB_A, "name": "公开库", "user_id": 2,
        "visibility": "public", "status": "active",
        "index_status": "ready", "index_generation": 1,
    }
    base.update(overrides)
    return KnowledgeBase(**base)


def _doc(**overrides):

    base = {
        "id": 20, "uuid": DOC_A, "kb_id": 10, "filename": "权限设计文档.pdf",
        "display_name": "权限设计文档", "status": "completed", "active_version": 1,
        "updated_at": datetime(2026, 8, 3, 9, 0, 0),
    }
    base.update(overrides)
    return Document(**base)


def _version(**overrides):

    base = {
        "id": 31, "uuid": VER_A1, "document_id": 20, "version": 1,
        "status": "ready", "published_at": datetime(2026, 8, 3, 10, 0, 0),
    }
    base.update(overrides)
    return DocumentVersion(**base)


def _chunk(**overrides):

    base = {
        "id": 41, "doc_id": 20, "kb_id": 10, "document_version_id": 31,
        "segment_uuid": SEG_A1, "chunk_index": 0, "chroma_id": "c1",
        "content": "KB 的 READ 权限决定该用户是否可检索。",
        "metadata_": {"page": 3, "section_title": "权限矩阵"},
    }
    base.update(overrides)
    return Chunk(**base)


# ---------------- RED 验收测试 ----------------

class TestRetrievalSearchEndpoint:
    SEARCH_URL = "/internal/v1/retrieval/search"

    @pytest.mark.asyncio
    async def test_missing_service_auth_returns_401(self, contract_client, service_auth):
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(""))
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_SERVICE_UNAUTHENTICATED"
        assert not list(validator_for("error-response").iter_errors(body))

    @pytest.mark.asyncio
    async def test_unsupported_contract_version_returns_400(self, contract_client, service_auth):
        headers = _headers(_service_token(service_auth))
        headers["X-EvidSight-Contract-Version"] = "2.0.0"
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_missing_request_metadata_returns_400(self, contract_client, service_auth):
        headers = _headers(_service_token(service_auth))
        del headers["traceparent"]
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_malformed_body_returns_400(self, contract_client, service_auth):
        headers = _headers(_service_token(service_auth))
        headers["Content-Type"] = "application/json"
        response = await contract_client.post(self.SEARCH_URL, content="{not-json", headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_body_missing_required_field_returns_400(self, contract_client, service_auth):
        body = _search_body()
        del body["query"]
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_body_invalid_uuid_returns_400(self, contract_client, service_auth):
        body = _search_body(knowledge_base_ids=["not-a-uuid"])
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_body_unknown_field_returns_400(self, contract_client, service_auth):
        body = _search_body(role="admin", visibility="public")
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_body_contract_version_mismatch_returns_400(self, contract_client, service_auth):
        # contracts/README §5：正文 contract_version 与版本头不一致 → INTERNAL_CONTRACT_UNSUPPORTED
        body = _search_body(contract_version="2.0.0")
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_empty_query_returns_400(self, contract_client, service_auth):
        # retrieval-request.schema.json：query minLength=1
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(query=""), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_query_too_long_returns_400(self, contract_client, service_auth):
        # retrieval-request.schema.json：query maxLength=8192
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(query="x" * 8193), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.parametrize(
        "filters",
        [
            {"languages": ["zh"]},
            {"updated_since": "2026-01-01T00:00:00Z"},
            {"updated_until": "2026-01-02T00:00:00Z"},
            {"languages": ["zh"], "updated_since": "2026-01-01T00:00:00Z",
             "updated_until": "2026-01-02T00:00:00Z"},
        ],
    )
    @pytest.mark.asyncio
    async def test_unimplemented_filters_rejected_returns_400(self, contract_client, service_auth, filters):
        # CHANGELOG「不做静默错误」：未实现的过滤字段语义 → 拒绝而非忽略
        body = _search_body(filters=filters)
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_INVALID"

    @pytest.mark.asyncio
    async def test_disabled_user_returns_403(self, contract_client, fake_db, service_auth):
        fake_db.seed(__import__("app.models.user", fromlist=["User"]).User, _user(status="disabled"))
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"

    @pytest.mark.asyncio
    async def test_missing_user_returns_403(self, contract_client, fake_db, service_auth):
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "AUTH_USER_DISABLED"

    @pytest.mark.asyncio
    async def test_kb_not_found_returns_403(self, contract_client, fake_db, service_auth):
        fake_db.seed(__import__("app.models.user", fromlist=["User"]).User, _user())
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_kb_not_readable_returns_403(self, contract_client, fake_db, service_auth):
        fake_db.seed(User, _user())
        fake_db.seed(__import__("app.models.knowledge_base", fromlist=["KnowledgeBase"]).KnowledgeBase,
                     _kb(uuid=KB_OTHER, user_id=2, visibility="private"))
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(knowledge_base_ids=[KB_OTHER]), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_any_kb_forbidden_fails_whole_request(self, contract_client, fake_db, service_auth):
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, [_kb(), _kb(uuid=KB_OTHER, id=12, user_id=2, visibility="private")])
        body = _search_body(knowledge_base_ids=[KB_A, KB_OTHER])
        response = await contract_client.post(self.SEARCH_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_kb_deleting_returns_403(self, contract_client, fake_db, service_auth):
        # DATABASE.md §5.1：deleting 状态立即拒绝 Internal Retrieval（失败关闭）
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(status="deleting"))
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_kb_index_not_ready_returns_503(self, contract_client, fake_db, service_auth, monkeypatch):
        # ADR-007：updating 有界等待后仍未收敛 → 503 可重试；缩短等待窗避免测试空等
        monkeypatch.setattr(settings, "PUBLISH_LOCK_WAIT_MS", 100)
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(index_status="updating"))
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_RETRIEVAL_UNAVAILABLE"
        assert body["error"]["retryable"] is True

    @pytest.mark.asyncio
    async def test_kb_updating_then_ready_waits_and_succeeds(
        self, contract_client, fake_db, service_auth, monkeypatch,
    ):
        """updating（发布锁持有中）→ 有界等待 → refresh 收敛为 ready → 检索放行。

        对齐 RAG_PIPELINE.md §4.2：发布窗口内检索不直接 503，等待原子切换完成。
        """
        from app.rag.retriever import RetrievalOutput, RetrievalResult
        from app.services import internal_retrieval

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(index_status="updating"))
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        fake_db.seed(Chunk, _chunk())

        async def fake_retrieve(db, kb_id, query, top_k=20, document_ids=None):
            return RetrievalOutput(
                results=[RetrievalResult(doc_id=20, chunk_index=0, content="正文", score=0.02)],
                total=1, fusion_method="rrf",
            )
        monkeypatch.setattr(internal_retrieval, "_retrieve_kb", fake_retrieve)

        refresh_calls = {"n": 0}

        async def _converge(instance):
            refresh_calls["n"] += 1
            instance.index_status = "ready"

        fake_db.refresh = _converge

        response = await contract_client.post(
            self.SEARCH_URL, json=_search_body(),
            headers=_headers(_service_token(service_auth)),
        )
        assert response.status_code == 200, response.text
        assert refresh_calls["n"] >= 1

    @pytest.mark.asyncio
    async def test_kb_recovering_returns_503_immediately(self, contract_client, fake_db, service_auth):
        """recovering 为不可恢复状态：不做有界等待，直接 503 可重试。"""
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(index_status="recovering"))
        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_RETRIEVAL_UNAVAILABLE"
        assert body["error"]["retryable"] is True

    @pytest.mark.asyncio
    async def test_success_returns_200_schema_compliant(self, contract_client, fake_db, service_auth, monkeypatch):
        from app.rag.retriever import RetrievalOutput, RetrievalResult
        from app.services import internal_retrieval

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        fake_db.seed(Chunk, _chunk())

        async def fake_retrieve(db, kb_id, query, top_k=20, document_ids=None):
            return RetrievalOutput(
                results=[RetrievalResult(doc_id=20, chunk_index=0, content="KB 的 READ 权限决定该用户是否可检索。", score=0.02)],
                total=1, fusion_method="rrf",
            )

        monkeypatch.setattr(internal_retrieval, "_retrieve_kb", fake_retrieve)

        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 200, response.text
        body = response.json()
        assert not list(validator_for("retrieval-response").iter_errors(body))
        assert len(body["results"]) == 1
        hit = body["results"][0]
        assert hit["knowledge_base_id"] == KB_A
        assert hit["document_id"] == DOC_A
        assert hit["document_version_id"] == VER_A1
        assert hit["segment_id"] == SEG_A1
        # 命中对象不得暴露内部实现字段
        forbidden = {"query_plan", "chunk_text", "file_path", "cache_key", "embedding", "collection"}
        assert not (set(hit) & forbidden)

    @pytest.mark.asyncio
    async def test_success_empty_results_returns_200(self, contract_client, fake_db, service_auth, monkeypatch):
        from app.rag.retriever import RetrievalOutput
        from app.services import internal_retrieval

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())

        async def fake_retrieve(db, kb_id, query, top_k=20, document_ids=None):
            return RetrievalOutput(results=[], total=0)

        monkeypatch.setattr(internal_retrieval, "_retrieve_kb", fake_retrieve)

        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 200, response.text
        body = response.json()
        assert not list(validator_for("retrieval-response").iter_errors(body))
        assert body["results"] == [] and body["returned_count"] == 0

    @pytest.mark.asyncio
    async def test_retrieval_failure_returns_503(self, contract_client, fake_db, service_auth, monkeypatch):
        from app.services import internal_retrieval

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())

        async def fake_retrieve(db, kb_id, query, top_k=20, document_ids=None):
            raise RuntimeError("检索链路不可用")

        monkeypatch.setattr(internal_retrieval, "_retrieve_kb", fake_retrieve)

        response = await contract_client.post(self.SEARCH_URL, json=_search_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["error_code"] == "INTERNAL_RETRIEVAL_UNAVAILABLE"
        assert body["error"]["retryable"] is True


class TestResolveEndpoint:
    RESOLVE_URL = "/internal/v1/retrieval/resolve"

    @pytest.mark.asyncio
    async def test_success_returns_200_schema_compliant(self, contract_client, fake_db, service_auth):

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        fake_db.seed(Chunk, _chunk())

        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 200, response.text
        body = response.json()
        assert not list(validator_for("evidence-resolve-response").iter_errors(body))
        resolved = body["results"][0]
        assert resolved["knowledge_base_id"] == KB_A
        assert resolved["document_id"] == DOC_A
        assert resolved["document_version_id"] == VER_A1
        assert resolved["segment_id"] == SEG_A1

    @pytest.mark.asyncio
    async def test_resolve_body_contract_version_mismatch_returns_400(self, contract_client, service_auth):
        # contracts/README §5：正文 contract_version 与版本头不一致 → INTERNAL_CONTRACT_UNSUPPORTED
        body = _resolve_body(contract_version="2.0.0")
        response = await contract_client.post(self.RESOLVE_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "INTERNAL_CONTRACT_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_segment_without_location_returns_evidence_unavailable(self, contract_client, fake_db, service_auth):
        # P5：无真实定位信息（page/section_path 均缺）→ 拒绝，而非伪造 section_path=["来源"]
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        fake_db.seed(Chunk, _chunk(metadata_={}))

        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "EVIDENCE_SOURCE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_kb_not_readable_returns_403(self, contract_client, fake_db, service_auth):
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(uuid=KB_OTHER, user_id=2, visibility="private"))
        body = _resolve_body(references=[{
            "knowledge_base_id": KB_OTHER, "document_id": DOC_A,
            "document_version_id": VER_A1, "segment_id": SEG_A1,
        }])
        response = await contract_client.post(self.RESOLVE_URL, json=body, headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_kb_deleting_returns_403(self, contract_client, fake_db, service_auth):
        # DATABASE.md §5.1：deleting 状态立即拒绝 Internal Retrieval（失败关闭）
        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb(status="deleting"))
        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 403
        assert response.json()["error"]["error_code"] == "KB_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_version_not_active_returns_evidence_unavailable(self, contract_client, fake_db, service_auth):

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc(active_version=2))  # 当前 Active 为版本 2
        fake_db.seed(DocumentVersion, _version(version=1))
        fake_db.seed(Chunk, _chunk())

        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "EVIDENCE_SOURCE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_segment_missing_returns_evidence_unavailable(self, contract_client, fake_db, service_auth):

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        # 不 seed Chunk → segment 缺失

        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "EVIDENCE_SOURCE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_any_reference_fails_whole_batch(self, contract_client, fake_db, service_auth):

        fake_db.seed(User, _user())
        fake_db.seed(KnowledgeBase, _kb())
        fake_db.seed(Document, _doc())
        fake_db.seed(DocumentVersion, _version())
        fake_db.seed(Chunk, _chunk())
        # 第二个引用指向不存在的 segment → 整批失败，不返回部分结果
        references = [
            {"knowledge_base_id": KB_A, "document_id": DOC_A, "document_version_id": VER_A1, "segment_id": SEG_A1},
            {"knowledge_base_id": KB_A, "document_id": DOC_A, "document_version_id": VER_A1, "segment_id": SEG_A2},
        ]
        response = await contract_client.post(self.RESOLVE_URL, json=_resolve_body(references=references), headers=_headers(_service_token(service_auth)))
        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "EVIDENCE_SOURCE_UNAVAILABLE"
