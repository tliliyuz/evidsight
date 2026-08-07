"""Fixture 校验：有效 Fixture 全部通过 Schema（含语义不变量），无效 Fixture 被 Schema 或语义不变量拒绝。"""

import pytest

from conftest import FIXTURES_DIR
from evidsight_contracts import semantics
from evidsight_contracts.loader import list_fixtures, load_fixture, validator_for


def _schemas_with_fixtures() -> list[str]:
    """从 fixtures/v1/valid/ 目录派生已有 valid fixture 的 Schema 名（新 Schema 自动纳入）。"""
    base = FIXTURES_DIR / "valid"
    return sorted(p.name for p in base.iterdir() if p.is_dir() and any(p.glob("*.json")))


@pytest.mark.parametrize(
    "schema_name, fixture_name",
    [
        (name, fixture)
        for name in _schemas_with_fixtures()
        for fixture in list_fixtures(name, "valid")
    ],
)
def test_valid_fixture_passes(schema_name, fixture_name):
    """CI 门禁 §12.3：有效 Fixture 必须通过 Schema 验证与语义不变量。"""
    validator = validator_for(schema_name)
    fixture = load_fixture(schema_name, "valid", fixture_name)
    errors = sorted(validator.iter_errors(fixture), key=str)
    assert not errors, f"{schema_name}/valid/{fixture_name} 应通过验证但失败:\n" + "\n".join(
        f"  - {e.message} (at {list(e.path)})" for e in errors
    )
    checker = semantics.SEMANTIC_CHECKERS.get(schema_name)
    if checker:
        violations = checker(fixture)
        assert not violations, (
            f"{schema_name}/valid/{fixture_name} 应通过语义不变量:\n" + "\n".join(violations)
        )


@pytest.mark.parametrize(
    "schema_name, fixture_name",
    [
        (name, fixture)
        for name in _schemas_with_fixtures()
        for fixture in list_fixtures(name, "invalid")
    ],
)
def test_invalid_fixture_rejected(schema_name, fixture_name):
    """CI 门禁 §12.3：无效 Fixture 必须被 Schema 或语义不变量拒绝。

    结构无效的 Fixture 由 Schema 拒绝；Schema 无法表达的跨字段不变量
    （Fixture 命名以 semantic- 前缀区分）由 semantics.SEMANTIC_CHECKERS 拒绝。
    """
    validator = validator_for(schema_name)
    fixture = load_fixture(schema_name, "invalid", fixture_name)
    schema_errors = list(validator.iter_errors(fixture))
    checker = semantics.SEMANTIC_CHECKERS.get(schema_name)
    semantic_violations = checker(fixture) if checker else []
    assert schema_errors or semantic_violations, (
        f"{schema_name}/invalid/{fixture_name} 应被拒绝但通过了 Schema 与语义校验"
    )
