"""Schema 自检：每个 JSON Schema 必须通过 JSON Schema 2020-12 Meta-Schema 校验。"""

import json

import pytest
from jsonschema import Draft202012Validator, exceptions

from conftest import SCHEMAS_DIR


def _all_schema_files():
    return sorted(p.name for p in SCHEMAS_DIR.glob("*.schema.json"))


@pytest.mark.parametrize("filename", _all_schema_files())
def test_schema_is_valid_against_meta_schema(filename):
    """CI 门禁 §12.1：JSON Schema 2020-12 Meta-Schema 校验。"""
    with (SCHEMAS_DIR / filename).open("r", encoding="utf-8") as f:
        schema = json.load(f)

    meta_schema = Draft202012Validator.META_SCHEMA
    validator = Draft202012Validator(meta_schema)
    errors = list(validator.iter_errors(schema))

    assert not errors, f"{filename} 不是合法 JSON Schema 2020-12:\n" + "\n".join(
        f"  - {err.message} (at {list(err.path)})" for err in errors
    )


def test_all_schema_ids_are_unique():
    """CI 门禁 §12.2：所有 $id 唯一。"""
    ids = []
    for filename in _all_schema_files():
        with (SCHEMAS_DIR / filename).open("r", encoding="utf-8") as f:
            schema = json.load(f)
        ids.append(schema.get("$id"))
    assert len(ids) == len(set(ids)), f"存在重复 $id: {ids}"
