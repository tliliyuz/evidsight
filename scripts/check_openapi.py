"""External OpenAPI 只读校验与保守 Breaking Change 检查。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate_spec
from openapi_spec_validator.readers import read_from_filename

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"OpenAPI 文档必须是对象：{path}")
    return document


def _validate_document(path: Path) -> dict[str, Any]:
    spec, base_uri = read_from_filename(str(path))
    validate_spec(spec, base_uri=base_uri)
    document = _load(path)
    _validate_examples(document)
    return document


def _walk_examples(node: Any):
    if isinstance(node, dict):
        schema = node.get("schema")
        if isinstance(schema, dict) and "example" in node:
            yield schema, node["example"]
        if isinstance(schema, dict) and isinstance(node.get("examples"), dict):
            for example in node["examples"].values():
                if isinstance(example, dict) and "value" in example:
                    yield schema, example["value"]
        for value in node.values():
            yield from _walk_examples(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_examples(value)


def _validate_examples(document: dict[str, Any]) -> None:
    for index, (schema, example) in enumerate(_walk_examples(document), start=1):
        materialized = _materialize_schema(document, schema)
        errors = sorted(
            Draft202012Validator(materialized).iter_errors(example),
            key=lambda error: list(error.path),
        )
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ValueError(f"OpenAPI 示例 #{index} 不符合 Schema：{detail}")


def _materialize_schema(
    document: dict[str, Any], value: Any, seen: frozenset[str] = frozenset()
) -> Any:
    """展开示例 Schema 使用的本地引用，交给标准 JSON Schema validator。"""
    if isinstance(value, list):
        return [_materialize_schema(document, item, seen) for item in value]
    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        if reference in seen:
            return value
        target = _resolve(document, {"$ref": reference})
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if siblings and isinstance(target, dict):
            target = {**target, **siblings}
        return _materialize_schema(document, target, seen | {reference})
    return {key: _materialize_schema(document, item, seen) for key, item in value.items()}


def _load_git_baseline(ref: str, relative_path: str) -> dict[str, Any] | None:
    if not ref or set(ref) == {"0"}:
        return None
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    document = yaml.safe_load(result.stdout)
    return document if isinstance(document, dict) else None


def _repository_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"OpenAPI 文档必须位于仓库内：{path}") from exc


def _resolve(document: dict[str, Any], value: Any) -> Any:
    seen: set[str] = set()
    while isinstance(value, dict) and set(value) == {"$ref"}:
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/") or reference in seen:
            return value
        seen.add(reference)
        target: Any = document
        for token in reference[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            target = target[token]
        value = target
    return value


def _operations(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                operations[(method, path)] = operation
    return operations


def _schema_breaks(
    baseline_document: dict[str, Any],
    current_document: dict[str, Any],
    baseline_schema: Any,
    current_schema: Any,
    location: str,
) -> list[str]:
    baseline_schema = _resolve(baseline_document, baseline_schema)
    current_schema = _resolve(current_document, current_schema)
    if not isinstance(baseline_schema, dict) or not isinstance(current_schema, dict):
        return []

    breaks: list[str] = []
    if baseline_schema.get("type") != current_schema.get("type"):
        breaks.append(
            f"{location} 类型从 {baseline_schema.get('type')} 改为 {current_schema.get('type')}"
        )

    baseline_enum = set(baseline_schema.get("enum", []))
    current_enum = set(current_schema.get("enum", []))
    if baseline_enum and not baseline_enum.issubset(current_enum):
        breaks.append(f"{location} 删除枚举值 {sorted(baseline_enum - current_enum)}")

    baseline_properties = baseline_schema.get("properties", {})
    current_properties = current_schema.get("properties", {})
    if isinstance(baseline_properties, dict) and isinstance(current_properties, dict):
        for name in sorted(set(baseline_properties) - set(current_properties)):
            breaks.append(f"{location} 删除字段 {name}")
        for name in sorted(set(baseline_properties) & set(current_properties)):
            breaks.extend(
                _schema_breaks(
                    baseline_document,
                    current_document,
                    baseline_properties[name],
                    current_properties[name],
                    f"{location}.{name}",
                )
            )

    new_required = set(current_schema.get("required", [])) - set(
        baseline_schema.get("required", [])
    )
    for name in sorted(new_required):
        breaks.append(f"{location} 新增必填字段 {name}")
    return breaks


def _breaking_changes(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    breaks: list[str] = []
    baseline_operations = _operations(baseline)
    current_operations = _operations(current)
    for operation in sorted(set(baseline_operations) - set(current_operations)):
        breaks.append(f"删除操作 {operation[0].upper()} {operation[1]}")

    baseline_schemas = baseline.get("components", {}).get("schemas", {})
    current_schemas = current.get("components", {}).get("schemas", {})
    if isinstance(baseline_schemas, dict) and isinstance(current_schemas, dict):
        for name in sorted(set(baseline_schemas) - set(current_schemas)):
            breaks.append(f"删除组件 Schema {name}")
        for name in sorted(set(baseline_schemas) & set(current_schemas)):
            breaks.extend(
                _schema_breaks(
                    baseline,
                    current,
                    baseline_schemas[name],
                    current_schemas[name],
                    f"components.schemas.{name}",
                )
            )
    return breaks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--baseline-ref", default="")
    args = parser.parse_args()

    current = _validate_document(args.spec)
    baseline = _load_git_baseline(args.baseline_ref, _repository_relative_path(args.spec))
    if baseline is None:
        print("OpenAPI 语法、$ref 与示例校验通过；当前无可比较的受保护基线。")
        return 0

    breaks = _breaking_changes(baseline, current)
    if breaks:
        print("检测到 OpenAPI Breaking Change：", file=sys.stderr)
        for item in breaks:
            print(f"- {item}", file=sys.stderr)
        return 1
    print("OpenAPI 语法、$ref、示例与 Breaking Change 检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
