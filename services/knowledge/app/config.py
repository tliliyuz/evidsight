"""应用配置 — 字段声明与 .env 变量自动映射，提供类型校验和 IDE 补全"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """pydantic-settings 自动从 CWD 读取 .env，将变量名匹配到以下字段。
    这里声明的值仅作「默认值」，.env 中存在同名变量时会被覆盖。"""

    model_config = {
        "env_file": Path(__file__).parent.parent / ".env",  # 相对 config.py 定位
        "env_file_encoding": "utf-8",
    }

    # 应用
    APP_NAME: str = "DocMind"
    DEBUG: bool = True
    ENV: str = "development"  # development / production

    # MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "docmind"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_BATCH_SIZE: int = 100

    # Embedding
    EMBED_BATCH_SIZE: int = 10  # DashScope text-embedding-v3 单次上限 10 条
    DEBUG_CHUNK_FULL: bool = False

    # LLM (OpenAI 兼容)
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-v4-pro"
    LLM_FLASH_MODEL: str = "deepseek-v4-flash"  # 轻量任务（意图分类/问题改写/标题生成）

    # Embedding
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-v3"

    # Rerank (DashScope)
    RERANK_API_KEY: str = ""
    RERANK_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    RERANK_MODEL: str = "qwen3-rerank"
    RERANK_MAX_RETRIES: int = 3
    RERANK_TIMEOUT: int = 30  # DashScope Rerank API 请求超时（秒）

    # JWT
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    EVIDSIGHT_PLATFORM_JWT_ISSUER: str = "evidsight"
    EVIDSIGHT_PLATFORM_JWT_AUDIENCES: str = "evidsight-knowledge,evidsight-research"
    EVIDSIGHT_KNOWLEDGE_JWT_AUDIENCE: str = "evidsight-knowledge"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # access_token 短有效期（对齐 API.md §2）
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # refresh_token 长有效期
    REFRESH_TOKEN_SECRET_KEY: str = ""  # 空则回退到 JWT_SECRET_KEY

    # ── Refresh Cookie / CSRF（事件③，对齐 ADR-006 / CONFIGURATION.md §3.1）──
    # `__Host-` 前缀强制要求 Path=/（RFC 6265bis §5.5），故 Path 默认 `/`；
    # Cookie 仍只被 /api/v1/auth/refresh 与 /api/v1/auth/logout 作为凭据读取。
    EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME: str = "__Host-evidsight_refresh"
    EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH: str = "/"
    EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE: bool = True
    EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = (
        "lax"  # 跨站部署用 none 且必须 Secure
    )
    EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME: str = "evidsight_csrf"
    EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS: str = ""  # csv string，生产必填（严格 Origin 校验）
    EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT: bool = (
        False  # M1 迁移期 body refresh_token 兼容入口
    )

    # ── Service JWT（服务间认证，对齐 CONFIGURATION.md §3）──
    EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER: str = "evidsight-platform"
    EVIDSIGHT_PLATFORM_SERVICE_JWT_ALGORITHM: str = "RS256"
    EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE: str = "knowledge-internal"
    EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS: int = Field(
        default=60, ge=10, le=300
    )  # 范围 10—300
    EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE: str = ""  # path, sensitive；必填

    @property
    def platform_jwt_audiences(self) -> list[str]:
        """返回统一 Access Token 的目标服务集合。"""
        return [
            audience.strip()
            for audience in self.EVIDSIGHT_PLATFORM_JWT_AUDIENCES.split(",")
            if audience.strip()
        ]

    @property
    def auth_allowed_origins(self) -> list[str]:
        """解析 Refresh/Logout 的严格 Origin 白名单；为空时按同站处理（开发环境）。"""
        return [
            origin.strip()
            for origin in self.EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_INGEST_QUEUE: str = "knowledge.ingest"
    CELERY_DELETE_QUEUE: str = "knowledge.delete"

    # 文件存储
    UPLOAD_DIR: str = "./uploads"
    UPLOAD_MAX_SIZE: int = 52428800  # 50MB，单位字节
    ALLOWED_EXTENSIONS: str = "pdf,docx,md,txt"  # 逗号分隔，可通过 .env 覆盖

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"  # 逗号分隔多个来源

    # ── Token Budget（四池子分拆，对齐 ARCHITECTURE.md §8.1）──
    MAX_CONTEXT_TOKENS: int = 20000
    SYSTEM_BUDGET: int = 2000
    HISTORY_BUDGET: int = 6000
    RETRIEVAL_BUDGET: int = 10000
    QUESTION_BUDGET: int = 2000
    HISTORY_MAX_MESSAGES: int = 20

    # ── Chunking ──
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    TOKEN_CHINESE_RATIO: float = 1.5  # 中文场景 token/字符 比率
    TOKEN_ENGLISH_RATIO: float = 4.0  # 英文场景 token/字符 比率
    TOKEN_CHINESE_THRESHOLD: float = 0.3  # 中文占比阈值（超过则使用中文比率）

    # ── Cleaning（M2 RAG 数据清洗）──
    CLEAN_ENABLED: bool = True  # 总开关：False 则跳过 Clean 阶段（行为与现状一致）
    CLEAN_STRIP_BOILERPLATE: bool = True  # 页码/页眉页脚去除
    CLEAN_NORMALIZE_WHITESPACE: bool = True  # 空白规整 + 安全折行拼接
    CLEAN_REPAIR_UNICODE: bool = True  # U+FFFD / mojibake 修复

    # ── Retrieval ──
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    BM25_MIN_SCORE: float = -5.0
    BM25_CACHE_TTL: int = 300
    BM25_LOCAL_CACHE_TTL: int = 60  # 进程内 BM25 缓存 TTL（秒）
    BM25_LOCAL_CACHE_MAX_CHUNKS: int = 5000  # 进程内缓存 chunk 数上限，超过则仅用 Redis 缓存
    BM25_MAX_CHUNKS: int = (
        10000  # BM25 硬限制：chunk 数超过此值的 KB 完全跳过 BM25 检索（避免 OOM）
    )
    BM25_SECTION_BOOST_FACTOR: float = 2.0  # §8.8 章节号匹配时 BM25 分数加权倍率

    # ── RRF ──
    RRF_K: int = 60

    # ── CoarseRank（ADR-024）──
    COARSE_RANK_ENABLED: bool = True  # 粗排开关
    COARSE_RANK_THRESHOLD: float = 0.05  # 余弦相似度最小阈值
    COARSE_TOP_K: int = 10  # 粗排后最大候选数

    # ── Reranker ──
    RERANK_TOP_K: int = 5

    # ── Prompt ──
    PROMPT_MAX_CHUNKS: int = 5
    PROMPT_MAX_CONTEXT_TOKENS: int = 3000

    # ── Query Rewrite ──
    REWRITE_MIN_LENGTH: int = 2  # Rewrite 结果最短有效长度
    REWRITE_HISTORY_MESSAGES: int = 4  # Rewrite 使用的最近历史消息数

    # ── Intent ──
    INTENT_MAX_TOKENS: int = 10  # 意图分类 LLM max_tokens

    # ── Embedding ──
    EMBED_MAX_RETRIES: int = 5
    EMBED_BASE_DELAY: int = 1
    EMBED_TIMEOUT: int = 60  # DashScope API 请求超时（秒）

    # ── Idempotency ──
    IDEMPOTENCY_LOCK_TTL: int = 600

    # ── Versioning / Publish（对齐 ADR-007）──
    PUBLISH_LOCK_WAIT_MS: int = 5000  # 检索对 updating KB 的有界等待上限（毫秒）
    STUCK_VERSION_TIMEOUT: int = 300  # 版本非终态停留超时（秒），超时重投递 ingest_version
    KB_LOCK_TIMEOUT: int = 600  # KB 发布锁（updating/recovering）停留超时（秒），超时恢复

    # ── Parsing ──
    PARSE_FAILURE_PARTIAL: float = 0.2
    PARSE_FAILURE_FAILED: float = 0.5

    # ── SSE ──
    SSE_HEARTBEAT_INTERVAL: int = 15

    # ── Document ──
    CHUNK_PREVIEW_LENGTH: int = 200
    BATCH_UPLOAD_MAX_COUNT: int = 50  # 批量上传单次最大文件数

    # ── 限流（对齐 ARCHITECTURE.md §13.2）──
    RATE_LIMIT_ENABLED: bool = True  # 限流开关
    RATE_LIMIT_CHAT_PER_MINUTE: int = (
        60  # 聊天接口（2026-06-18 压测推算，见 tests/performance/STRESS_TEST_REPORT.md §3）
    )
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 20  # 上传接口
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10  # 登录接口
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 120  # 其他接口
    RATE_LIMIT_WINDOW_SECONDS: int = 60  # 窗口大小（秒）

    @property
    def mysql_url(self) -> str:
        """构造异步 MySQL 连接串（强制会话 time_zone=UTC，确保 CURRENT_TIMESTAMP 返回 UTC）"""
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?init_command=SET time_zone='%2B00:00'"
        )


settings = Settings()
