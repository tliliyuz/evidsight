"""OpenAPI CI 的保守兼容性检查验收。"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check_openapi.py"
SPEC = importlib.util.spec_from_file_location("check_openapi", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _document(*, required: list[str] | None = None, enum: list[str] | None = None) -> dict:
    property_schema: dict = {"type": "string"}
    if enum is not None:
        property_schema["enum"] = enum
    return {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "get": {"responses": {"200": {"description": "ok"}}},
            }
        },
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "required": required or [],
                    "properties": {"status": property_schema},
                }
            }
        },
    }


def test_breaking_change_detects_removed_operation():
    baseline = _document()
    current = _document()
    current["paths"] = {}

    assert "删除操作 GET /items" in MODULE._breaking_changes(baseline, current)


def test_breaking_change_detects_required_field_and_narrowed_enum():
    baseline = _document(enum=["active", "disabled"])
    current = _document(required=["status"], enum=["active"])

    breaks = MODULE._breaking_changes(baseline, current)

    assert "components.schemas.Item 新增必填字段 status" in breaks
    assert "components.schemas.Item.status 删除枚举值 ['disabled']" in breaks


def test_additive_operation_is_compatible():
    baseline = _document()
    current = _document()
    current["paths"]["/items"]["post"] = {"responses": {"201": {"description": "created"}}}

    assert MODULE._breaking_changes(baseline, current) == []


def test_absolute_spec_path_is_converted_for_git_baseline_lookup():
    spec_path = ROOT / "docs" / "openapi" / "evidsight-v1.yaml"

    assert MODULE._repository_relative_path(spec_path) == "docs/openapi/evidsight-v1.yaml"
