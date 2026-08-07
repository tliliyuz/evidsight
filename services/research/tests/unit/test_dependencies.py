"""依赖注入单元测试 —— get_current_user / require_task_accessible。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.exceptions import InvalidTokenException
from app.dependencies import get_current_user
from fastapi import Request


class TestGetCurrentUser:
    """get_current_user 对 request.state 缺失的防护。"""

    @pytest.mark.asyncio
    async def test_request_state缺失user_id_抛出E1004(self):
        request = MagicMock(spec=Request)
        request.state = type("State", (), {"user_id": None})()
        db = AsyncMock()

        with pytest.raises(InvalidTokenException) as exc:
            await get_current_user(request, db)

        assert exc.value.error_code == "E1004"

    @pytest.mark.asyncio
    async def test_request_state无user_id属性_抛出E1004(self):
        request = MagicMock(spec=Request)
        request.state = type("State", (), {})()
        db = AsyncMock()

        with pytest.raises(InvalidTokenException) as exc:
            await get_current_user(request, db)

        assert exc.value.error_code == "E1004"
        assert "缺少用户认证信息" in exc.value.error_detail["error_description"]

    @pytest.mark.asyncio
    async def test_正常返回用户字典(self):
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.user_id = "550e8400-e29b-41d4-a716-446655440000"
        request.state.username = "testuser"
        request.state.role = "user"

        db = AsyncMock()
        result = await get_current_user(request, db)

        assert result == {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "platform_user_id": "550e8400-e29b-41d4-a716-446655440000",
            "username": "testuser",
            "role": "user",
        }
        db.get.assert_not_called()
