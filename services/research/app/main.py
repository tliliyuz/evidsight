"""
ResearchMind FastAPI 入口。

- 创建 FastAPI 实例，配置 CORS 中间件
- 注册全局异常处理器
- 提供 /api/health 健康检查端点
- 后续 Phase 引入路由（auth / research）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import research, research_evidence, research_v1
from app.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import setup_logging
from app.metrics import (
    CONTENT_TYPE_LATEST,
    get_metrics_output,
    setup_metrics,
    shutdown_metrics,
)
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.middleware.request_id_middleware import RequestIDMiddleware
from app.tasks.celery_app import celery_app
from app.tasks.recovery import recover_stale_tasks

logger = logging.getLogger(__name__)


# ── 生命周期管理 ──────────────────────────────────────────


async def _recover_stale_tasks() -> None:
    """启动时恢复过时 running 任务 + pending 重投递。

    与 Worker 就绪、周期 Beat、手动治理调用同一恢复服务（纯 DB lease，不依赖 Redis）。
    失败不阻塞应用启动。
    """
    try:
        recovered = await recover_stale_tasks()
        if recovered:
            logger.warning(
                "启动恢复：已重新投递 %d 个过时 running 任务: %s",
                len(recovered),
                recovered,
            )
    except Exception:
        logger.exception("启动时过时任务恢复失败，不阻塞应用启动")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动 / 关闭时的生命周期事件。"""
    logger.info(
        f"🚀 {settings.APP_NAME} v0.1.0 启动中... (env={settings.ENV}, debug={settings.DEBUG})"
    )
    await setup_metrics()
    await _recover_stale_tasks()
    yield
    await shutdown_metrics()
    logger.info(f"👋 {settings.APP_NAME} 已关闭")


# ── 结构化日志（JSON 格式 + request_id 链路追踪） ──────────

setup_logging(debug=settings.DEBUG)

# ── FastAPI 实例 ──────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS 中间件 ───────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request ID 中间件（链路追踪 contextvars 注入） ─────────

app.add_middleware(RequestIDMiddleware)

# ── Auth 中间件（JWT 验证，写入 request.state） ──────────────

app.add_middleware(AuthMiddleware)

# ── 限流中间件（固定窗口计数器 + Redis 原子操作） ───────────

app.add_middleware(RateLimitMiddleware)

# ── 全局异常处理器 ───────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic 请求校验失败 → E9003 (422)。"""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "code": "E9003",
            "message": "请求参数校验失败",
            "detail": {
                "error_type": "ValidationError",
                "error_description": "请求参数校验失败，请检查输入",
                "errors": errors,
            },
        },
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """AppException → 对应 HTTP 状态码。

    AppException 已通过 HTTPException.detail 携带完整响应体
    （{"code", "message", "detail"}），Starlette 对 dict 类型的 detail
    直接作为 JSON 响应体返回。
    """
    logger.warning(
        "业务异常: code=%s, message=%s, status=%d",
        exc.error_code,
        exc.error_message,
        exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未预期异常 → E9001 (500)。"""
    logger.exception(f"未预料的服务器内部错误: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "E9001",
            "message": "服务器内部错误",
            "detail": {
                "error_type": "InternalError",
                "error_description": "服务器内部错误，请稍后重试",
            },
        },
    )


# ── 健康检查 ─────────────────────────────────────────────


@app.get("/api/health", tags=["系统"])
async def health_check():
    """健康检查端点。"""
    return {
        "code": "0",
        "message": "ok",
        "data": {"status": "healthy"},
    }


@app.get("/api/health/workers", tags=["系统"])
async def worker_health_check():
    """Worker 集群健康检查端点。"""
    try:
        pings = celery_app.control.ping(timeout=5.0) or []
    except Exception as e:
        logger.exception("Worker 健康检查失败")
        return {
            "code": "0",
            "message": "ok",
            "data": {
                "status": "unknown",
                "worker_count": 0,
                "workers": [],
                "error": str(e),
            },
        }

    workers: list[str] = []
    for ping in pings:
        if isinstance(ping, dict):
            workers.extend(ping.keys())

    status = "healthy" if workers else "no_workers"
    return {
        "code": "0",
        "message": "ok",
        "data": {
            "status": status,
            "worker_count": len(workers),
            "workers": workers,
        },
    }


# ── Metrics 端点 ──────────────────────────────────────────


@app.get(settings.METRICS_ENDPOINT, include_in_schema=False)
async def metrics_endpoint():
    """Prometheus 指标抓取端点。"""
    return Response(content=get_metrics_output(), media_type=CONTENT_TYPE_LATEST)


# ── 路由注册 ──────────────────────────────────────────────

app.include_router(research.router, prefix="/api/research")
app.include_router(research_v1.router, prefix="/api/v1/research")
app.include_router(research_evidence.router, prefix="/api/v1")
