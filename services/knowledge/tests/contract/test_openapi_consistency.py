"""三方一致性校验 — FastAPI 路由清单 ↔ docs/openapi/evidsight-v1.yaml ↔ Provider 契约测试。

对齐 ROADMAP M2 退出门禁「docs/openapi/evidsight-v1.yaml 至少覆盖上述 Knowledge
v1 路径，且 FastAPI 路由清单、OpenAPI 路径清单与 Provider 契约测试三方一致」。

覆盖范围：Knowledge FastAPI App 的全部浏览器外部 /api/v1/* 路径。双向比对
YAML ⊆ 路由 ∧ 路由 ⊆ YAML，并断言每条 YAML 操作已被显式登记的契约测试文件覆盖。
不得通过业务前缀白名单只检查当前切片。
"""

from pathlib import Path

from app.main import app

from tests.contract.openapi_utils import find_openapi_path, load_openapi

# Knowledge App 的全部浏览器外部 v1 API；Research/Evidence/Report 由 Research App
# 的对应一致性门禁负责，Internal 与 legacy 不在本文件范围。
PREFIXES = ("/api/v1",)
RESEARCH_PREFIXES = ("/api/v1/research", "/api/v1/evidence", "/api/v1/reports")

# 每条 OpenAPI 操作 → 覆盖它的契约测试文件（仓库根相对路径）。
# 新增/调整 v1 端点时必须同步更新本表，否则三方一致校验失败。
COVERAGE: dict[tuple[str, str], str] = {
    ("post", "/api/v1/knowledge-bases"): "tests/contract/test_knowledge_v1_api.py",
    ("get", "/api/v1/knowledge-bases"): "tests/contract/test_knowledge_v1_api.py",
    ("get", "/api/v1/knowledge-bases/{kb_id}"): "tests/contract/test_knowledge_v1_api.py",
    ("patch", "/api/v1/knowledge-bases/{kb_id}"): "tests/contract/test_knowledge_v1_api.py",
    ("delete", "/api/v1/knowledge-bases/{kb_id}"): "tests/contract/test_knowledge_v1_api.py",
    ("post", "/api/v1/knowledge-bases/{kb_id}/documents"): "tests/contract/test_document_v1_api.py",
    ("get", "/api/v1/knowledge-bases/{kb_id}/documents"): "tests/contract/test_document_v1_api.py",
    ("get", "/api/v1/documents/{document_id}"): "tests/contract/test_document_v1_api.py",
    ("delete", "/api/v1/documents/{document_id}"): "tests/contract/test_document_v1_api.py",
    ("get", "/api/v1/documents/{document_id}/chunks"): "tests/contract/test_document_v1_api.py",
    ("post", "/api/v1/documents/{document_id}/retry"): "tests/contract/test_document_v1_api.py",
    (
        "get",
        "/api/v1/documents/{document_id}/locations/{location_id}",
    ): "tests/unit/api/test_document_location_api.py",
    ("post", "/api/v1/conversations"): "tests/contract/test_conversation_v1_api.py",
    ("get", "/api/v1/conversations"): "tests/contract/test_conversation_v1_api.py",
    (
        "get",
        "/api/v1/conversations/{conversation_id}",
    ): "tests/contract/test_conversation_v1_api.py",
    (
        "patch",
        "/api/v1/conversations/{conversation_id}",
    ): "tests/contract/test_conversation_v1_api.py",
    (
        "delete",
        "/api/v1/conversations/{conversation_id}",
    ): "tests/contract/test_conversation_v1_api.py",
    ("post", "/api/v1/auth/register"): "tests/unit/api/test_auth_api.py",
    ("post", "/api/v1/auth/login"): "tests/unit/api/test_auth_api.py",
    ("post", "/api/v1/auth/refresh"): "tests/unit/api/test_auth_api.py",
    ("post", "/api/v1/auth/logout"): "tests/unit/api/test_auth_api.py",
    ("get", "/api/v1/auth/me"): "tests/unit/api/test_auth_api.py",
    ("put", "/api/v1/auth/password"): "tests/unit/api/test_auth_api.py",
    ("post", "/api/v1/chat/stream"): "tests/unit/api/test_chat_v1.py",
    (
        "post",
        "/api/v1/chat/generations/{generation_id}/cancel",
    ): "tests/unit/api/test_chat_v1.py",
}

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _yaml_operations() -> set[tuple[str, str]]:
    """从 OpenAPI 提取 (method, path)，仅保留覆盖前缀内的路径。"""
    spec = load_openapi()
    ops: set[tuple[str, str]] = set()
    for path, item in spec["paths"].items():
        if not path.startswith(PREFIXES) or path.startswith(RESEARCH_PREFIXES):
            continue
        for method in item:
            if method in _HTTP_METHODS:
                ops.add((method, path))
    return ops


def _fastapi_operations() -> set[tuple[str, str]]:
    """从 FastAPI openapi() 提取 (method, path)，仅保留覆盖前缀内的路径。"""
    ops: set[tuple[str, str]] = set()
    for path, item in app.openapi()["paths"].items():
        if not path.startswith(PREFIXES) or path.startswith(RESEARCH_PREFIXES):
            continue
        for method in item:
            if method in _HTTP_METHODS:
                ops.add((method, path))
    return ops


def _repo_root() -> Path:
    return find_openapi_path().parents[2]


class TestOpenAPIConsistency:
    def test_yaml_operations_subset_of_routes(self):
        """OpenAPI 声明的每条 v1 操作都必须已注册到 FastAPI 路由。"""
        yaml_ops = _yaml_operations()
        fastapi_ops = _fastapi_operations()
        missing_in_routes = yaml_ops - fastapi_ops
        assert not missing_in_routes, (
            f"OpenAPI 已声明但 FastAPI 未注册: {sorted(missing_in_routes)}"
        )

    def test_routes_subset_of_yaml(self):
        """FastAPI 已注册的每条 v1 操作都必须已在 OpenAPI 中声明（不注册未契约化的路由）。"""
        yaml_ops = _yaml_operations()
        fastapi_ops = _fastapi_operations()
        not_in_yaml = fastapi_ops - yaml_ops
        assert not not_in_yaml, f"FastAPI 已注册但 OpenAPI 未声明: {sorted(not_in_yaml)}"

    def test_all_yaml_operations_covered_by_contract_tests(self):
        """OpenAPI 每条操作都有对应的契约测试文件，且测试文件存在。"""
        repo_root = _repo_root()
        yaml_ops = _yaml_operations()
        for op in yaml_ops:
            assert op in COVERAGE, f"OpenAPI 操作缺少契约测试登记: {op}"
        for test_file in set(COVERAGE.values()):
            assert (repo_root / test_file).is_file(), f"契约测试文件不存在: {test_file}"

    def test_openapi_is_valid_3_1_document(self):
        """OpenAPI 文档结构合法：3.1.0、info、paths、components.schemas 齐全。"""
        spec = load_openapi()
        assert spec["openapi"].startswith("3.1")
        assert spec["info"]["title"]
        assert "paths" in spec
        assert "components" in spec
        assert "schemas" in spec["components"]
