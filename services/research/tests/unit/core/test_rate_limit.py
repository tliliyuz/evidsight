"""限流中间件测试 — 覆盖 app/middleware/rate_limit_middleware.py。

对齐 ROADMAP.md §5.5：
- 限流未超限 → 放行并注入 X-RateLimit-* 响应头
- 限流超限 → 429 + E9004 + Retry-After 信息
- Redis 不可用 → 降级放行
- OPTIONS / docs / health 路径跳过
- RATE_LIMIT_ENABLED=False 时直通
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.middleware.rate_limit_middleware import RateLimitMiddleware


# ── 辅助：创建带限流中间件的测试应用 ──


def _make_test_app():
    """创建含限流中间件的最小 FastAPI 应用"""
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/test")
    async def test_endpoint():
        return {"data": "ok"}

    @app.post("/api/research")
    async def create_research():
        return {"task_id": "new-task"}

    @app.post("/api/auth/login")
    async def login():
        return {"token": "abc"}

    return app


# ═══════════════════════════════════════════════════════════════
# 集成测试：通过 TestClient + 挂载中间件验证中间件行为
# ═══════════════════════════════════════════════════════════════


class TestRateLimitUnderLimit:
    """未超限 — 请求正常放行"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_未超限返回200并注入限流响应头(self, mock_get_redis):
        """Redis INCR 返回 1 ≤ limit → 请求正常处理 + 注入 X-RateLimit-* 头"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 1  # 当前计数为 1，未超限
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120
            mock_settings.RATE_LIMIT_RESEARCH_PER_MINUTE = 5
            mock_settings.RATE_LIMIT_LOGIN_PER_MINUTE = 10

            client = TestClient(app)
            response = client.get("/api/test")

            assert response.status_code == 200
            assert response.json()["data"] == "ok"
            # 应注入限流响应头
            assert "x-ratelimit-limit" in response.headers
            assert "x-ratelimit-remaining" in response.headers
            assert "x-ratelimit-reset" in response.headers
            limit_val = int(response.headers["x-ratelimit-limit"])
            remaining_val = int(response.headers["x-ratelimit-remaining"])
            assert limit_val == 120  # default group
            assert remaining_val == 119  # limit - current = 120 - 1


class TestRateLimitExceeded:
    """超限 — 返回 429"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_超限返回429且错误码为E9004(self, mock_get_redis):
        """Redis INCR 返回 121 > limit(120) → 429 E9004"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 121  # 超限
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120
            mock_settings.RATE_LIMIT_RESEARCH_PER_MINUTE = 5
            mock_settings.RATE_LIMIT_LOGIN_PER_MINUTE = 10

            client = TestClient(app)
            response = client.get("/api/test")

            assert response.status_code == 429
            body = response.json()
            assert body["code"] == "E9004"
            assert "限流" in body["message"] or "频率" in body["message"]
            # 超限响应头
            assert response.headers["x-ratelimit-remaining"] == "0"
            assert "x-ratelimit-reset" in response.headers
            assert "x-ratelimit-limit" in response.headers

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_research接口超限使用对应阈值(self, mock_get_redis):
        """POST /api/research 使用 research 组阈值 5/min"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 6  # 超过 research 阈值 5
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120
            mock_settings.RATE_LIMIT_RESEARCH_PER_MINUTE = 5
            mock_settings.RATE_LIMIT_LOGIN_PER_MINUTE = 10

            client = TestClient(app)
            response = client.post("/api/research")

            assert response.status_code == 429
            limit_val = int(response.headers["x-ratelimit-limit"])
            assert limit_val == 5  # research 组阈值

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_login接口超限使用对应阈值(self, mock_get_redis):
        """POST /api/auth/login 使用 login 组阈值 10/min"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 11  # 超过 login 阈值 10
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120
            mock_settings.RATE_LIMIT_RESEARCH_PER_MINUTE = 5
            mock_settings.RATE_LIMIT_LOGIN_PER_MINUTE = 10

            client = TestClient(app)
            response = client.post("/api/auth/login")

            assert response.status_code == 429
            limit_val = int(response.headers["x-ratelimit-limit"])
            assert limit_val == 10  # login 组阈值


class TestRateLimitSkip:
    """跳过路径 — 不触发限流检查"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_OPTIONS请求跳过限流(self, mock_get_redis):
        """OPTIONS 预检请求不触发限流（CORS 预检），无论应用如何处理"""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            client = TestClient(app)
            # FastAPI 可能返回 405（未定义 OPTIONS handler），
            # 但限流中间件应在检查 Redis 之前就跳过 OPTIONS
            response = client.options("/api/test")

            # 关键验证：Redis 未被调用（限流逻辑被完全跳过）
            mock_redis.eval.assert_not_called()

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_health端点跳过限流(self, mock_get_redis):
        """/api/health 健康检查不触发限流"""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            client = TestClient(app)
            response = client.get("/api/health")

            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            mock_redis.eval.assert_not_called()

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_docs路径跳过限流(self, mock_get_redis):
        """/docs Swagger UI 不触发限流"""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            client = TestClient(app)
            response = client.get("/docs")

            # /docs 返回 200（Swagger HTML）或 404 都行，关键是 Redis 未被调用
            mock_redis.eval.assert_not_called()


class TestRateLimitDisabled:
    """限流关闭 — 所有请求直通"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_RATE_LIMIT_ENABLED为False时直通(self, mock_get_redis):
        """RATE_LIMIT_ENABLED=False 时所有请求不经过限流检查"""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = False

            client = TestClient(app)
            response = client.get("/api/test")
            assert response.status_code == 200
            mock_redis.eval.assert_not_called()

            response2 = client.post("/api/research")
            assert response2.status_code == 200
            mock_redis.eval.assert_not_called()


class TestRateLimitRedisDegradation:
    """Redis 不可用 — 降级放行"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_Redis异常时降级放行不阻塞请求(self, mock_get_redis):
        """Redis 操作抛出异常时降级放行，请求正常完成"""
        mock_get_redis.side_effect = ConnectionError("Redis 连接失败")

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120

            client = TestClient(app)
            response = client.get("/api/test")

            # 降级放行 → 正常响应
            assert response.status_code == 200
            assert response.json()["data"] == "ok"
            # 降级时不应注入限流头
            assert "x-ratelimit-limit" not in response.headers

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_Redis返回非数字不阻塞请求(self, mock_get_redis):
        """Redis eval 返回非数字值时降级放行"""
        mock_redis = AsyncMock()
        mock_redis.eval.side_effect = ValueError("无法解析为整数")
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            client = TestClient(app)
            response = client.get("/api/test")

            # 降级放行 → 正常响应
            assert response.status_code == 200


class TestRateLimitNonApiPaths:
    """非 API 路径 — 不触发限流"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_非api前缀路径跳过限流(self, mock_get_redis):
        """非 /api 前缀的路径不触发限流检查"""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()

        @app.get("/")
        async def home():
            return {"home": True}

        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            client = TestClient(app)
            response = client.get("/")

            assert response.status_code == 200
            mock_redis.eval.assert_not_called()


class TestIPExtraction:
    """IP 提取 — 测试 X-Forwarded-For / X-Real-IP / 直连 IP"""

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_XForwardedFor取第一个IP(self, mock_get_redis):
        """多级代理时取 X-Forwarded-For 第一个 IP"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 1
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120

            client = TestClient(app)
            response = client.get(
                "/api/test",
                headers={"X-Forwarded-For": "192.168.1.100, 10.0.0.1, 172.16.0.1"},
            )

            assert response.status_code == 200
            # 验证 Redis key 包含第一个 IP
            # eval(script, numkeys, key, ttl) → call_args[0][2] 是 key
            call_args = mock_redis.eval.call_args
            key = call_args[0][2]  # KEYS[1]（第 3 个位置参数）
            assert "192.168.1.100" in key

    @patch("app.middleware.rate_limit_middleware.get_async_redis")
    def test_XRealIP作为来源IP(self, mock_get_redis):
        """无 X-Forwarded-For 时使用 X-Real-IP"""
        mock_redis = AsyncMock()
        mock_redis.eval.return_value = 1
        mock_get_redis.return_value = mock_redis

        app = _make_test_app()
        app.add_middleware(RateLimitMiddleware)

        with patch("app.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.RATE_LIMIT_DEFAULT_PER_MINUTE = 120

            client = TestClient(app)
            response = client.get(
                "/api/test",
                headers={"X-Real-IP": "10.10.10.10"},
            )

            assert response.status_code == 200
            call_args = mock_redis.eval.call_args
            key = call_args[0][2]  # KEYS[1]（第 3 个位置参数）
            assert "10.10.10.10" in key
