"""OpenAPI 契约测试共享工具 — 加载 docs/openapi/evidsight-v1.yaml 并校验响应 DTO。

供 v1 Provider 契约测试与三方一致性测试复用。路径从测试文件向上定位
docs/openapi/evidsight-v1.yaml（兼容宿主机与容器内 /app 布局）。
"""

from pathlib import Path

import yaml


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


def assert_data_matches_schema(schema_name: str, data: dict) -> None:
    """断言响应 data 对象字段与 OpenAPI 组件 Schema 一致。

    必需字段必须全部存在，且不允许出现 Schema 未定义的字段。用于验证
    FastAPI 实现输出的 DTO 与 docs/openapi/evidsight-v1.yaml 定义的契约一致。
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
