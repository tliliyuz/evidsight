"""禁用用户全链路拒绝测试 — IA-005

对齐 IDENTITY_AND_ACCESS.md §6「用户禁用语义」与 TESTING.md §3.2：
- 新建 Chat、上传、重处理和治理写操作失败；
- 统一返回 401 E5010，业务逻辑不得执行。

覆盖两层：
1. 依赖层（get_current_user）：以 mock DB 查询语义验证 active/不存在/disabled 分支；
2. API 层：override get_current_user 抛 UserDisabledException，验证 Chat、单个上传、
   批量上传、重处理、治理写操作（禁用/启用用户、重置密码）均被 401 E5010 拒绝。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import UserDisabledException
from app.dependencies import get_current_user
from app.models.user import User


# ==================== 测试用 UUID 常量 ====================
# 对齐 conftest 尾号推导约定：尾号 1 → user_id 1（普通用户），2 → admin。
PLATFORM_UUID = "550e8400-e29b-41d4-a716-446655440001"
KB_UUID = "11111111-1111-4111-8111-111111111111"
DOC_UUID = "22222222-2222-4222-8222-222222222222"
ADMIN_TARGET_UUID = "550e8400-e29b-41d4-a716-446655440003"


def _make_result(user):
    """构造 DB execute 结果对象：scalar_one_or_none 同步返回指定用户。

    execute 为 async（await db.execute），scalar_one_or_none 为同步调用，
    使用 MagicMock 避免 AsyncMock 生成未 await 的 coroutine（对齐现有
    test_auth_service._make_mock_result 做法）。
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=user)
    return result


def _make_user(status="active", role="user"):
    """构造 User 模型实例（get_current_user 依赖层测试用）。"""
    return User(
        id=1,
        platform_user_id=PLATFORM_UUID,
        username="testuser",
        role=role,
        status=status,
        password_hash="x",
    )


def _make_request(role="user"):
    """构造携带 platform_user_id 与 role 的 mock Request。"""
    request = AsyncMock()
    request.state.platform_user_id = PLATFORM_UUID
    request.state.role = role
    return request


async def _request_with_disabled_user(async_client, method, url, **kwargs):
    """override get_current_user 抛 UserDisabledException 后发起请求，断言 401 E5010。

    若目标路由未经过 get_current_user（禁用检查缺失），异常不会触发，
    请求将落入业务逻辑并返回非 401/E5010 响应，测试因断言失败而 RED。
    """
    from app.main import app

    async def _disabled_user():
        raise UserDisabledException()

    app.dependency_overrides[get_current_user] = _disabled_user
    try:
        response = await getattr(async_client, method)(url, **kwargs)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 401
    assert response.json()["code"] == "E5010"
    return response


class TestGetCurrentUserDisabledGate:
    """依赖层：get_current_user 对不存在/禁用用户抛 UserDisabledException（E5010）。"""

    @pytest.mark.asyncio
    async def test_active_user_passes(self, mock_db):
        """active 用户通过，返回由数据库当前状态构建的用户信息。"""
        mock_db.execute.return_value = _make_result(_make_user("active"))
        result = await get_current_user(_make_request(), mock_db)
        assert result["user_id"] == 1
        assert result["platform_user_id"] == PLATFORM_UUID
        assert result["role"] == "user"

    @pytest.mark.asyncio
    async def test_disabled_user_raises_5010(self, mock_db):
        """status=disabled 用户抛 401 E5010。"""
        mock_db.execute.return_value = _make_result(_make_user("disabled"))
        with pytest.raises(UserDisabledException) as exc:
            await get_current_user(_make_request(), mock_db)
        assert exc.value.error_code == "E5010"
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_raises_5010(self, mock_db):
        """用户不存在与禁用统一抛 401 E5010（不区分语义）。"""
        mock_db.execute.return_value = _make_result(None)
        with pytest.raises(UserDisabledException) as exc:
            await get_current_user(_make_request(), mock_db)
        assert exc.value.error_code == "E5010"


class TestDisabledUserRejectedAtApi:
    """API 层：禁用用户对 Chat/上传/重处理/治理写操作均返回 401 E5010。"""

    @pytest.mark.asyncio
    async def test_chat_creation_rejected(self, async_client, auth_headers):
        """新建 Chat：禁用用户被拒绝，不进入 SSE 业务。"""
        await _request_with_disabled_user(
            async_client,
            "post",
            "/api/chat",
            headers=auth_headers,
            json={
                "kb_id": KB_UUID,
                "question": "hello",
                "conversation_id": None,
                "deep_thinking": False,
            },
        )

    @pytest.mark.asyncio
    async def test_upload_document_rejected(self, async_client, auth_headers):
        """上传单个文档：禁用用户被拒绝，不落盘不入队。"""
        await _request_with_disabled_user(
            async_client,
            "post",
            f"/api/knowledge-bases/{KB_UUID}/documents",
            headers=auth_headers,
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )

    @pytest.mark.asyncio
    async def test_batch_upload_rejected(self, async_client, auth_headers):
        """批量上传文档：禁用用户被拒绝。"""
        await _request_with_disabled_user(
            async_client,
            "post",
            f"/api/knowledge-bases/{KB_UUID}/documents/batch-upload",
            headers=auth_headers,
            files=[
                ("files", ("a.txt", b"a", "text/plain")),
                ("files", ("b.txt", b"b", "text/plain")),
            ],
        )

    @pytest.mark.asyncio
    async def test_reprocess_document_rejected(self, async_client, auth_headers):
        """重新处理文档：禁用用户被拒绝。"""
        await _request_with_disabled_user(
            async_client,
            "post",
            f"/api/knowledge-bases/{KB_UUID}/documents/{DOC_UUID}/reprocess",
            headers=auth_headers,
        )

    @pytest.mark.asyncio
    async def test_admin_status_write_rejected(self, async_client, admin_auth_headers):
        """治理写操作（禁用/启用用户）：被禁用的 admin 被拒绝。"""
        await _request_with_disabled_user(
            async_client,
            "put",
            f"/api/admin/users/{ADMIN_TARGET_UUID}/status",
            headers=admin_auth_headers,
            json={"status": "disabled"},
        )

    @pytest.mark.asyncio
    async def test_admin_reset_password_rejected(self, async_client, admin_auth_headers):
        """治理写操作（重置密码）：被禁用的 admin 被拒绝。"""
        await _request_with_disabled_user(
            async_client,
            "post",
            f"/api/admin/users/{ADMIN_TARGET_UUID}/reset-password",
            headers=admin_auth_headers,
            json={"new_password": "NewPass123!"},
        )
