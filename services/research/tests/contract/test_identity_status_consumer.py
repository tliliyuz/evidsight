"""Internal Identity Status 契约 — Research 作为 Consumer 的验收测试。

对齐 API.md §11.1、contracts/README.md §5.1、TESTING.md IA-012。
Consumer 测试独立运行：只读取 packages/contracts 的 Schema 与 Fixture，
不依赖 Knowledge 端点、数据库或服务导入。
"""
import pytest

from evidsight_contracts.loader import (
    list_fixtures,
    load_fixture,
    validator_for,
)


def _validator():
    return validator_for("identity-status-response")


class TestIdentityStatusConsumer:
    VALID = list_fixtures("identity-status-response", "valid")
    INVALID = list_fixtures("identity-status-response", "invalid")

    def test_consumer_can_parse_valid_identity_status(self):
        """有效 Fixture 全部通过 Schema 校验（active 用户的最小响应）。"""
        assert self.VALID, "identity-status-response 至少需要一个 valid fixture"
        for name in self.VALID:
            errors = list(_validator().iter_errors(load_fixture("identity-status-response", "valid", name)))
            assert not errors, f"{name} 应通过校验但失败:\n{errors}"

    @pytest.mark.parametrize(
        "fixture_name",
        [f for f in list_fixtures("identity-status-response", "invalid") if f.startswith("missing-")],
    )
    def test_consumer_rejects_missing_required_fields(self, fixture_name):
        """缺少必填字段的响应被拒绝。"""
        errors = list(_validator().iter_errors(load_fixture("identity-status-response", "invalid", fixture_name)))
        assert errors, f"{fixture_name} 缺少必填字段但通过了校验"

    @pytest.mark.parametrize(
        "fixture_name",
        [f for f in list_fixtures("identity-status-response", "invalid") if f.startswith("wrong-type-")],
    )
    def test_consumer_rejects_wrong_types(self, fixture_name):
        """字段类型错误的响应被拒绝。"""
        errors = list(_validator().iter_errors(load_fixture("identity-status-response", "invalid", fixture_name)))
        assert errors, f"{fixture_name} 类型错误但通过了校验"

    def test_consumer_rejects_negative_status_version(self):
        """status_version 为负数的响应被拒绝。"""
        errors = list(_validator().iter_errors(
            load_fixture("identity-status-response", "invalid", "negative-status-version")
        ))
        assert errors, "negative-status-version 应被拒绝但通过了校验"

    def test_consumer_rejects_unknown_status_enum(self):
        """status 非 active 的响应被拒绝（禁用/不存在用户走错误响应）。"""
        errors = list(_validator().iter_errors(
            load_fixture("identity-status-response", "invalid", "unknown-status-enum")
        ))
        assert errors, "unknown-status-enum 应被拒绝但通过了校验"

    @pytest.mark.parametrize(
        "fixture_name",
        [f for f in list_fixtures("identity-status-response", "invalid") if f.startswith("extra-field-")],
    )
    def test_consumer_rejects_extra_profile_fields(self, fixture_name):
        """额外用户资料字段（username/role/email/internal_id）被 Schema 拒绝。"""
        errors = list(_validator().iter_errors(load_fixture("identity-status-response", "invalid", fixture_name)))
        assert errors, f"{fixture_name} 含禁止字段但通过了校验"

    def test_consumer_runs_independently(self):
        """Consumer 测试可独立运行：仅通过文件系统读取 Schema 与 Fixture，无 HTTP/DB 依赖。"""
        schema = _validator().schema
        assert "contract_version" in schema.get("properties", {})
        assert schema.get("additionalProperties") is False
        # 所有 fixture 文件可读
        assert self.VALID and self.INVALID
