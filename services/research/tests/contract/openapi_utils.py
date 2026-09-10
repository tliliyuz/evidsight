"""Research OpenAPI 契约测试共享工具 — 加载 docs/openapi/evidsight-v1.yaml 并校验响应 DTO 与 SSE 事件。

对齐 TESTING.md §4：External OpenAPI 除路径双向一致外，还必须逐事件校验
Chat/Research SSE 的事件名、顺序与每种 data Schema。本模块复刻 Knowledge
`tests/contract/openapi_utils.py` 的 `load_openapi`/`assert_data_matches_schema`，
并补充：
- `materialize_schema_ref`：把 `$ref` 深展开为无引用的实际 schema dict；
- `load_sse_event_schemas`：读取 OpenAPI 指定路径/方法的 `x-sse-data-schemas` 映射；
- `assert_sse_events`：解析 SSE 文本并对每帧 data 用 jsonschema 逐事件校验。

路径从测试文件向上定位 docs/openapi/evidsight-v1.yaml（兼容宿主机与容器内 /app 布局）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml  # type: ignore[import-untyped]


def find_openapi_path() -> Path:
    """从本文件所在目录向上定位 docs/openapi/evidsight-v1.yaml。"""
    start = Path(__file__).resolve().parent
    for parent in [start] + list(start.parents):
        candidate = parent / "docs" / "openapi" / "evidsight-v1.yaml"
        if candidate.is_file():
            return candidate
    raise RuntimeError("无法定位 docs/openapi/evidsight-v1.yaml")


def load_openapi() -> dict:
    """加载 OpenAPI 3.1.0 定义（YAML → dict）。"""
    return yaml.safe_load(find_openapi_path().read_text(encoding="utf-8"))


def _expand_ref(spec: dict, node: Any, _seen: set[str] | None = None) -> Any:
    """深展开 schema 树中的全部 `$ref`，返回无引用的纯 dict。

    本仓库 schema 的 `$ref` 全部指向 `#/components/schemas/X`。展开后
    jsonschema 无需 Resolver/Registry 即可直接校验，规避内存 spec 上
    相对片段引用解析的边界问题。
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/components/schemas/"):
                raise ValueError(f"不支持的 $ref: {ref}")
            name = ref.rsplit("/", 1)[-1]
            if _seen is None:
                _seen = set()
            if name in _seen:
                raise ValueError(f"$ref 循环引用: {name}")
            try:
                target = spec["components"]["schemas"][name]
            except KeyError:
                raise AssertionError(f"OpenAPI 组件 Schema 不存在: {name}")
            resolved = _expand_ref(spec, target, _seen | {name})
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            if not siblings:
                return resolved
            # OAS 3.1 允许 $ref 携带兄弟关键字：合并（兄弟键优先被再次展开）
            return {
                **resolved,
                **{k: _expand_ref(spec, v, _seen | {name}) for k, v in siblings.items()},
            }
        return {k: _expand_ref(spec, v, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_ref(spec, item, _seen) for item in node]
    return node


def materialize_schema_ref(ref: str) -> dict:
    """把 `$ref` 字符串解析为实际 schema dict（深展开嵌套引用）。"""
    spec = load_openapi()
    resolved = _expand_ref(spec, {"$ref": ref})
    if not isinstance(resolved, dict):
        raise AssertionError(f"$ref 未解析为 object schema: {ref}")
    return resolved


def assert_data_matches_schema(schema_name: str, data: dict) -> None:
    """断言响应 data 对象字段与 OpenAPI 组件 Schema 一致（浅层）。

    必需字段必须全部存在，且不允许出现 Schema 未定义的字段。用于验证
    FastAPI 实现输出的 DTO 与 docs/openapi/evidsight-v1.yaml 定义的契约一致。
    嵌套对象（steps / report.sections / requirements 等）由测试内显式
    调用本函数或 `assert_sse_events` 做深层断言。
    """
    spec = load_openapi()
    try:
        schema = spec["components"]["schemas"][schema_name]
    except KeyError:
        raise AssertionError(f"OpenAPI 组件 Schema 不存在: {schema_name}")
    required = schema.get("required", [])
    props = set(schema["properties"].keys())
    data_keys = set(data.keys())
    missing = [k for k in required if k not in data_keys]
    assert not missing, f"{schema_name} 响应缺少必需字段: {missing}"
    extra = data_keys - props
    assert not extra, f"{schema_name} 响应出现未定义字段: {sorted(extra)}"


def assert_data_matches_schema_deep(schema_name: str, data: dict) -> None:
    """全量 jsonschema 校验响应 data 与组件 Schema（含值级与嵌套字段）。

    在 `assert_data_matches_schema` 的键级检查之上，进一步校验字段值类型、
    嵌套对象、枚举与 `additionalProperties` 约束。字段级契约测试据此
    捕获值级漂移（如 `Report.evidence_completeness` 类型声明与实现不一致）。
    """
    spec = load_openapi()
    try:
        schema = spec["components"]["schemas"][schema_name]
    except KeyError:
        raise AssertionError(f"OpenAPI 组件 Schema 不存在: {schema_name}")
    expanded = _expand_ref(spec, schema)
    errors = sorted(
        jsonschema.Draft7Validator(expanded).iter_errors(data),
        key=lambda e: (list(e.absolute_path), e.message),
    )
    assert not errors, f"{schema_name} 响应不符合 Schema:\n" + "\n".join(
        f"  {e.message} @ {list(e.absolute_path)}" for e in errors
    )


def load_sse_event_schemas(path: str, method: str) -> dict[str, dict]:
    """读取 OpenAPI 指定路径/方法的 `x-sse-data-schemas` 映射（单一事实源）。

    Returns:
        {事件名: schema dict}，schema dict 可能为 `{$ref: ...}` 或内联定义。
    """
    spec = load_openapi()
    op = (spec.get("paths") or {}).get(path, {}).get(method)
    assert op is not None, f"OpenAPI 未声明 {method.upper()} {path}"
    for resp in (op.get("responses") or {}).values():
        content = resp.get("content") or {}
        mapping = (content.get("text/event-stream") or {}).get("x-sse-data-schemas")
        if mapping is not None:
            return mapping
    raise AssertionError(
        f"OpenAPI {method.upper()} {path} 缺少 text/event-stream 的 x-sse-data-schemas"
    )


def parse_sse_events(sse_text: str) -> list[tuple[str | None, dict]]:
    """解析 SSE 文本为 [(event_name, data)] 事件列表，跳过注释帧。

    兼容 `format_sse_event` 与 v1 canonical 流两种形态：
    - 无 `id:` 的 `event: X\\ndata: {...}\\n\\n`；
    - 带 `id: N` 的 canonical 帧（`id:` 行被忽略，仅取 event/data）。
    多行 `data:` 行按 SSE 规范以 `\\n` 连接后整体 json.loads。
    """
    events: list[tuple[str | None, dict]] = []
    for block in sse_text.split("\n\n"):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if not data_lines:
            continue
        data = json.loads("\n".join(data_lines))
        events.append((event_name, data))
    return events


def assert_sse_events(
    sse_text: str,
    event_schemas: dict[str, dict],
    *,
    first_event: str | None = None,
    terminal_events: frozenset[str] = frozenset(),
) -> list[tuple[str, dict]]:
    """逐事件校验 SSE 流：事件名必须被 schema 覆盖，data 必须通过 jsonschema 校验。

    Args:
        sse_text: SSE 原始文本（可能包含心跳注释帧）。
        event_schemas: {事件名: schema dict}，来自 `load_sse_event_schemas`。
        first_event: 若指定，断言流首帧事件名。
        terminal_events: 若非空，断言流末帧事件名 ∈ 该集合。

    Returns:
        解析后的 [(event_name, data)]，供调用方继续断言顺序/首帧/终态。
    """
    spec = load_openapi()
    events = parse_sse_events(sse_text)
    assert events, "SSE 流为空或全为注释帧"
    # 每帧必须有 event 名才能按事件 schema 校验；无名帧（畸形流）fail-closed
    typed_events: list[tuple[str, dict]] = []
    for name, data in events:
        assert name is not None, "SSE 帧缺少 event 名，无法按事件 schema 校验"
        typed_events.append((name, data))
    names = [name for name, _ in typed_events]
    unknown = {name for name in names if name not in event_schemas}
    assert not unknown, f"SSE 出现未定义事件名: {sorted(unknown)}"
    for i, (name, data) in enumerate(typed_events):
        schema = _expand_ref(spec, event_schemas[name])
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(
            validator.iter_errors(data), key=lambda e: (list(e.absolute_path), e.message)
        )
        assert not errors, f"SSE 第 {i} 帧 event={name} data 不符合 Schema:\n" + "\n".join(
            f"  {e.message} @ {list(e.absolute_path)}" for e in errors
        )
    if first_event is not None:
        assert names[0] == first_event, f"SSE 首帧应为 {first_event}，实际 {names[0]}"
    if terminal_events:
        assert names[-1] in terminal_events, (
            f"SSE 末帧应为 {sorted(terminal_events)}，实际 {names[-1]}"
        )
    return typed_events
