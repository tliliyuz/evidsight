"""Schema 自检：所有 $ref 可解析，加载后能以 jsonschema Validator 构造。"""

import pytest

from conftest import SCHEMAS_DIR
from evidsight_contracts.loader import load_schema, validator_for


def _all_schema_names():
    return sorted(p.name.removesuffix(".schema.json") for p in SCHEMAS_DIR.glob("*.schema.json"))


@pytest.mark.parametrize("name", _all_schema_names())
def test_schema_loads_and_constructs_validator(name):
    """加载（含 $ref 重写）后能构造 Validator，说明引用可解析。"""
    # 构造成功即证明所有 $ref 在重写后均可解析（失败会抛异常）
    validator = validator_for(name)
    assert validator is not None


def test_no_relative_refs_after_load():
    """加载后不得残留相对 ./ 文件引用（跨文件 $ref 必须重写为 file:// 绝对路径）。

    同文档内部 #/$defs/... 片段引用是合法 JSON Schema，loader 不重写且按原样解析；
    本测试只禁止未重写的相对文件引用。
    """
    for name in _all_schema_names():
        schema = load_schema(name)

        def _collect(node):
            refs = []
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "$ref" and isinstance(v, str):
                        refs.append(v)
                    else:
                        refs.extend(_collect(v))
            elif isinstance(node, list):
                for item in node:
                    refs.extend(_collect(item))
            return refs

        refs = _collect(schema)
        assert all(not r.startswith("./") for r in refs), (
            f"{name} 存在未重写为绝对路径的相对 $ref: {refs}"
        )
