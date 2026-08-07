"""M1 Research 身份所有权验收测试。"""

import subprocess
import sys

import app.core.security as security
from app.main import app


def test_ia001b_research不暴露身份写接口():
    """注册、登录、刷新、退出和改密只能由 Knowledge 身份模块提供。"""
    auth_paths = {route.path for route in app.routes if route.path.startswith("/api/auth")}

    assert auth_paths == set()


def test_ia001b_research不拥有用户和刷新令牌表():
    """防止 Research 再次成为用户凭证或 Refresh Token 的事实源。"""
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.database import Base; import app.models; "
                "assert 'users' not in Base.metadata.tables; "
                "assert 'refresh_tokens' not in Base.metadata.tables"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_ia001b_research安全模块只验证access_token():
    """Research 不提供密码处理、Access Token 签发或 Refresh Token 能力。"""
    forbidden = {
        "hash_password",
        "verify_password",
        "create_access_token",
        "create_refresh_token",
        "decode_refresh_token",
        "hash_token",
    }

    assert forbidden.isdisjoint(vars(security))
