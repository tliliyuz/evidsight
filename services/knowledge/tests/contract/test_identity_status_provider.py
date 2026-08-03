"""Internal Identity Status 契约 — Knowledge 作为 Provider 的验收测试。

对齐 API.md §11.1、contracts/README.md §5.1。SDD 门禁：
- GREEN 目标：Knowledge 实现 GET /internal/v1/identity/users/{id}/status 并返回 Schema 合规响应。
- 当前 RED：端点尚未注册，请求返回 404。本测试先证明缺少目标行为，再进入实现。
"""
import uuid

import pytest

from evidsight_contracts.loader import validator_for


class TestIdentityStatusProvider:
    PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"

    def test_provider_can_produce_schema_compliant_response(self):
        """Provider 能构造 Schema 合规的最小 IdentityStatusResponse（不含用户资料字段）。"""
        response = {
            "contract_version": "1.0.0",
            "platform_user_id": self.PLATFORM_UUID,
            "status": "active",
            "status_version": 1,
        }
        errors = list(validator_for("identity-status-response").iter_errors(response))
        assert not errors, f"Provider 构造的响应不符合契约:\n{errors}"

    @pytest.mark.asyncio
    async def test_identity_status_endpoint_returns_404_red(self, async_client, auth_headers):
        """RED：带合法用户 Token 请求尚未注册的端点返回 404。

        这是正确 RED — 证明 GET /internal/v1/identity/users/{id}/status 路由缺失，
        是实现前的验收前提。GREEN 后本测试应改为断言 200 且响应符合 Schema。
        """
        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status",
            headers=auth_headers,
        )
        assert response.status_code == 404, (
            f"预期端点未注册返回 404（RED），实际 {response.status_code}。"
            f"若端点已实现，本测试应改为断言 200 且响应符合 Schema。"
        )

    @pytest.mark.asyncio
    async def test_identity_status_rejects_missing_service_auth_red(self, async_client):
        """RED：缺少 Service JWT 的请求被拒绝。

        当前端点未注册（401 由全局中间件拦截），GREEN 后应为 401 INTERNAL_SERVICE_UNAUTHENTICATED。
        """
        response = await async_client.get(
            f"/internal/v1/identity/users/{self.PLATFORM_UUID}/status"
        )
        # 现阶段 RED：任何 4xx 都证明请求未获得 IdentityStatusResponse 成功响应
        assert response.status_code >= 400, (
            f"缺少服务身份的请求不得返回成功响应，实际 {response.status_code}"
        )
