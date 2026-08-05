"""启动配置校验 — 生产环境 fail-fast（对齐 CONFIGURATION.md 生产必填项）。

在 FastAPI lifespan 启动时调用：生产环境（DEBUG=False）下配置缺失直接拒绝启动，
避免带病上线；开发环境仅不阻断本地迭代。readiness（/api/health/ready）复用
本模块的可加载检查作为关键依赖探针。
"""

from app.config import settings
from app.core.service_security import public_keys_loadable


def validate_production_config() -> list[str]:
    """生产配置校验，返回问题列表；空列表表示通过。

    开发环境（DEBUG=True）一律返回 []（不阻断本地迭代）；
    生产环境收集「AUTH_ALLOWED_ORIGINS 必填」「Service 公钥无法加载」两类错误。
    """
    if settings.DEBUG:
        return []

    errors: list[str] = []
    if not settings.EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS.strip():
        errors.append(
            "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS 生产环境必填，为空拒绝启动"
        )
    if not public_keys_loadable():
        errors.append(
            "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE 无法加载，"
            "Service JWT 验证将全部失败"
        )
    return errors
