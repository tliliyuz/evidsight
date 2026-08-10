"""Research Service 契约测试共享配置：复用 packages/contracts 的 loader。

契约测试关注 OpenAPI 响应字段契约，身份 Provider 属外部依赖（TESTING.md §1
边界 Mock），默认放行 `check_user_status`，避免字段级契约测试发起真实 HTTP。
"""

import sys
from pathlib import Path

import pytest


def _find_contracts_root() -> Path:
    """从本文件所在目录向上定位 packages/contracts 目录（兼容宿主机与容器内路径）。"""
    start = Path(__file__).resolve().parent
    for parent in [start] + list(start.parents):
        candidate = parent / "packages" / "contracts"
        if candidate.is_dir() and (candidate / "schemas" / "v1").is_dir():
            return candidate
    raise RuntimeError("无法定位 packages/contracts 目录")


_GENERATED_PY = _find_contracts_root() / "generated" / "python"
if str(_GENERATED_PY) not in sys.path:
    sys.path.insert(0, str(_GENERATED_PY))


@pytest.fixture(autouse=True)
def _identity_gate_ok(monkeypatch):
    """默认放行身份状态检查，契约测试不发起真实身份服务 HTTP。

    对齐 tests/unit/conftest.py 的 `_identity_gate_ok`：contract 目录独立运行
    （unit conftest 不覆盖此处），字段级契约测试的验收点是 OpenAPI 响应
    Schema，身份 Provider 在边界 Mock。
    """
    from unittest.mock import AsyncMock

    from app.services import research_service

    async def _ok(user_id: str):
        return None

    monkeypatch.setattr(
        research_service,
        "check_user_status",
        AsyncMock(side_effect=_ok),
        raising=False,
    )
