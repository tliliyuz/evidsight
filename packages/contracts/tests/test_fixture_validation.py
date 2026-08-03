"""Fixture 校验：有效 Fixture 全部通过 Schema，无效 Fixture 全部被拒绝。"""
import pytest

from evidsight_contracts.loader import list_fixtures, load_fixture, validator_for


@pytest.mark.parametrize(
    "schema_name, fixture_name",
    [
        (name, fixture)
        for name in ["identity-status-response", "error-response"]
        for fixture in list_fixtures(name, "valid")
    ],
)
def test_valid_fixture_passes(schema_name, fixture_name):
    """CI 门禁 §12.3：有效 Fixture 必须通过 Schema 验证。"""
    validator = validator_for(schema_name)
    fixture = load_fixture(schema_name, "valid", fixture_name)
    errors = sorted(validator.iter_errors(fixture), key=str)
    assert not errors, f"{schema_name}/valid/{fixture_name} 应通过验证但失败:\n" + "\n".join(
        f"  - {e.message} (at {list(e.path)})" for e in errors
    )


@pytest.mark.parametrize(
    "schema_name, fixture_name",
    [
        (name, fixture)
        for name in ["identity-status-response", "error-response"]
        for fixture in list_fixtures(name, "invalid")
    ],
)
def test_invalid_fixture_rejected(schema_name, fixture_name):
    """CI 门禁 §12.3：无效 Fixture 必须被 Schema 拒绝（至少一个验证错误）。"""
    validator = validator_for(schema_name)
    fixture = load_fixture(schema_name, "invalid", fixture_name)
    errors = list(validator.iter_errors(fixture))
    assert errors, f"{schema_name}/invalid/{fixture_name} 应被拒绝但通过了验证"
