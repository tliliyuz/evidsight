"""Research 外部 v1 路由 ↔ External OpenAPI 双向一致性门禁。

对齐 TESTING.md §4 与 ROADMAP M4 Provider 就绪门禁。覆盖 Research FastAPI App
供浏览器消费的全部 Research / Evidence / Report v1 路径；不得以当前切片前缀缩小范围。
字段级响应契约测试（真实路由响应逐字段对齐 OpenAPI Schema）登记在
test_research_v1_field_contract.py / test_research_evidence_field_contract.py，
SSE 逐事件 data Schema 校验在 test_research_sse_events.py；DELETE（204 无正文）
与事件名投影等行为契约保留在既有 unit 测试。
"""

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from app.main import app

PREFIXES = (
    "/api/v1/research",
    "/api/v1/evidence",
    "/api/v1/reports",
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

COVERAGE: dict[tuple[str, str], str] = {
    ("post", "/api/v1/research/tasks"): "tests/contract/test_research_v1_field_contract.py",
    ("get", "/api/v1/research/tasks"): "tests/contract/test_research_v1_field_contract.py",
    (
        "get",
        "/api/v1/research/tasks/{task_id}",
    ): "tests/contract/test_research_v1_field_contract.py",
    # DELETE 返回 204 无正文，行为契约保留在 unit 测试
    ("delete", "/api/v1/research/tasks/{task_id}"): "tests/unit/api/test_research_v1.py",
    (
        "post",
        "/api/v1/research/tasks/{task_id}/cancel",
    ): "tests/contract/test_research_v1_field_contract.py",
    (
        "post",
        "/api/v1/research/tasks/{task_id}/resume",
    ): "tests/contract/test_research_v1_field_contract.py",
    (
        "get",
        "/api/v1/research/tasks/{task_id}/state",
    ): "tests/contract/test_research_v1_field_contract.py",
    # SSE 事件名/顺序/data Schema 逐事件校验
    (
        "get",
        "/api/v1/research/tasks/{task_id}/events",
    ): "tests/contract/test_research_sse_events.py",
    (
        "get",
        "/api/v1/research/tasks/{task_id}/report",
    ): "tests/contract/test_research_v1_field_contract.py",
    (
        "get",
        "/api/v1/research/tasks/{task_id}/evidence",
    ): "tests/contract/test_research_evidence_field_contract.py",
    (
        "get",
        "/api/v1/evidence/{evidence_id}",
    ): "tests/contract/test_research_evidence_field_contract.py",
    (
        "get",
        "/api/v1/evidence/{evidence_id}/relations",
    ): "tests/contract/test_research_evidence_field_contract.py",
    (
        "get",
        "/api/v1/reports/{report_id}",
    ): "tests/contract/test_research_evidence_field_contract.py",
    (
        "get",
        "/api/v1/reports/{report_id}/sections/{section_id}",
    ): "tests/contract/test_research_evidence_field_contract.py",
}


def _find_openapi() -> Path:
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / "docs" / "openapi" / "evidsight-v1.yaml"
        if candidate.is_file():
            return candidate
    raise RuntimeError("无法定位 docs/openapi/evidsight-v1.yaml")


def _operations(paths: dict) -> set[tuple[str, str]]:
    return {
        (method, path)
        for path, item in paths.items()
        if path.startswith(PREFIXES)
        for method in item
        if method in HTTP_METHODS
    }


def _yaml_operations() -> set[tuple[str, str]]:
    spec = yaml.safe_load(_find_openapi().read_text(encoding="utf-8"))
    return _operations(spec["paths"])


def _fastapi_operations() -> set[tuple[str, str]]:
    return _operations(app.openapi()["paths"])


class TestResearchExternalOpenAPIRoutes:
    def test_openapi_operations_are_registered(self):
        missing = _yaml_operations() - _fastapi_operations()
        assert not missing, f"OpenAPI 已声明但 Research FastAPI 未注册: {sorted(missing)}"

    def test_registered_operations_are_in_openapi(self):
        missing = _fastapi_operations() - _yaml_operations()
        assert not missing, f"Research FastAPI 已注册但 OpenAPI 未声明: {sorted(missing)}"

    def test_all_operations_have_provider_contract_tests(self):
        missing = _yaml_operations() - set(COVERAGE)
        assert not missing, f"Research OpenAPI 操作缺少 Provider 契约测试登记: {sorted(missing)}"
        root = Path(__file__).resolve().parents[2]
        for relative_path in set(COVERAGE.values()):
            assert (root / relative_path).is_file(), f"契约测试文件不存在: {relative_path}"

    def test_2xx_json_responses_declare_content_schema(self):
        """对齐 TESTING.md §4：2xx/202 的 application/json 响应必须声明 content schema。

        204 无正文合法；text/event-stream 不在此检查范围。防止新增 Research 操作
        只声明描述不声明 Schema（如 /report 的兼容响应）。
        """
        spec = yaml.safe_load(_find_openapi().read_text(encoding="utf-8"))
        violations: list[str] = []
        for path, item in spec["paths"].items():
            if not path.startswith(PREFIXES):
                continue
            for method, op in item.items():
                if method not in HTTP_METHODS:
                    continue
                for status, resp in (op.get("responses") or {}).items():
                    if not (status.startswith("2") and status != "204"):
                        continue
                    content = resp.get("content") or {}
                    if "text/event-stream" in content:
                        continue
                    schema = (content.get("application/json") or {}).get("schema")
                    if schema is None:
                        violations.append(
                            f"{method.upper()} {path} {status}: application/json 响应缺少 content schema"
                        )
        assert not violations, "Research 2xx/202 JSON 响应必须声明 content schema:\n" + "\n".join(
            sorted(violations)
        )
