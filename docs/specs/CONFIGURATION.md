# CONFIGURATION — 配置规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 配置基线 |
| 最后更新 | 2026-08-03 |

## 1. 规则

- 每个配置键必须声明所有者、类型、必填性、默认值和安全级别；
- 生产密钥不得提供可用默认值；
- 未知键告警，类型或边界错误使启动/配置 smoke 失败；
- `.env.example` 只放键名和安全示例，不放真实凭证；
- 两个服务不得读取对方私有配置命名空间。

## 2. 命名空间

| 前缀 | 所有者 | 示例 |
|:---|:---|:---|
| `EVIDSIGHT_PLATFORM_` | 统一身份 | JWT issuer、audience、Key ID |
| `EVIDSIGHT_KNOWLEDGE_` | Knowledge | DB、Chroma、上传、队列 |
| `EVIDSIGHT_RESEARCH_` | Research | DB、租约、预算、队列 |
| `EVIDSIGHT_WEB_` | Web 构建 | API 基础路径、公开特性标志 |
| `EVIDSIGHT_PROVIDER_` | 外部 Provider | endpoint、model、credential reference |

## 3. 必需类别

- 数据库：独立 DSN、连接池、超时和 UTC；
- Redis：独立 DB、Key 前缀、队列名和 `noeviction` 要求；
- 身份：issuer、audience、算法、Key ID、Access/Refresh 生命周期、双 Key 窗口、Refresh Cookie/CSRF 浏览器传输和严格 Origin 校验；
- 文件/向量：上传路径、允许类型、大小、磁盘保护水位、Chroma 路径；
- Provider：能力开关、endpoint、model、超时、重试、并发、预算和外发策略；
- Research：租约时长、续租周期、Scanner 间隔、Task 并发、队列上限和单任务预算；
- 可观察性：日志级别、采样、指标开关和保留策略引用。

### 3.1 v1.0 配置键注册表

`secret` 表示值只能通过未提交环境或 Secret 注入；`sensitive` 表示可记录键名但不得记录值；`public` 表示可安全进入构建产物。时长统一使用秒，容量统一使用字节。

| 键 | 所有者 | 类型 | 必填/默认值 | 安全级别 |
|:---|:---|:---|:---|:---|
| `EVIDSIGHT_PLATFORM_JWT_ISSUER` | Platform | string | 必填 | public |
| `EVIDSIGHT_PLATFORM_JWT_AUDIENCES` | Platform | csv string | `evidsight-knowledge,evidsight-research` | public |
| `EVIDSIGHT_KNOWLEDGE_JWT_AUDIENCE` | Knowledge | string | `evidsight-knowledge` | public |
| `EVIDSIGHT_RESEARCH_JWT_AUDIENCE` | Research | string | `evidsight-research` | public |
| `EVIDSIGHT_PLATFORM_JWT_ALGORITHM` | Platform | enum | `RS256` | public |
| `EVIDSIGHT_PLATFORM_JWT_ACTIVE_KID` | Platform | string | 必填 | public |
| `EVIDSIGHT_PLATFORM_JWT_PRIVATE_KEY_FILE` | Platform | path | 签发端必填 | secret |
| `EVIDSIGHT_PLATFORM_JWT_PUBLIC_KEYS_FILE` | Knowledge/Research | path | 必填 | sensitive |
| `EVIDSIGHT_PLATFORM_ACCESS_TOKEN_TTL_SECONDS` | Platform | int | `900` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_TOKEN_TTL_SECONDS` | Platform | int | `604800` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME` | Platform | string | `__Host-evidsight_refresh` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH` | Platform | string | `/`（`__Host-` 前缀强制 Path=/，RFC 6265bis §5.5） | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE` | Platform | bool | `true` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE` | Platform | enum | `lax`；跨站部署用 `none` 且必须 `Secure` | public |
| `EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME` | Platform | string | `evidsight_csrf` | public |
| `EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS` | Platform | csv string | 必填（严格 Origin 校验） | public |
| `EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` | Platform | bool | `false`（M1 迁移期可开） | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER` | Platform | string | `evidsight-platform` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_ALGORITHM` | Platform | enum | `RS256` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE` | Platform | string | `knowledge-internal` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS` | Platform | int | `60`，范围 10—300 | public |
| `EVIDSIGHT_RESEARCH_SERVICE_JWT_ACTIVE_KID` | Research | string | 必填 | public |
| `EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE` | Research | path | 必填 | secret |
| `EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE` | Knowledge | path | 必填 | sensitive |
| `EVIDSIGHT_KNOWLEDGE_DATABASE_URL` | Knowledge | URL | 必填 | secret |
| `EVIDSIGHT_RESEARCH_DATABASE_URL` | Research | URL | 必填 | secret |
| `EVIDSIGHT_KNOWLEDGE_REDIS_URL` | Knowledge | URL | 必填 | secret |
| `EVIDSIGHT_RESEARCH_REDIS_URL` | Research | URL | 必填 | secret |
| `EVIDSIGHT_KNOWLEDGE_REDIS_PREFIX` | Knowledge | string | `evidsight:knowledge` | public |
| `EVIDSIGHT_RESEARCH_REDIS_PREFIX` | Research | string | `evidsight:research` | public |
| `CELERY_INGEST_QUEUE` | Knowledge | string | `knowledge.ingest` | public |
| `CELERY_DELETE_QUEUE` | Knowledge | string | `knowledge.delete` | public |
| `CELERY_EXECUTE_QUEUE` | Research | string | `research.execute` | public |
| `CELERY_PERIODIC_QUEUE` | Research | string | `research.periodic` | public |
| `EVIDSIGHT_KNOWLEDGE_UPLOAD_DIR` | Knowledge | path | 必填 | sensitive |
| `EVIDSIGHT_KNOWLEDGE_CHROMA_DIR` | Knowledge | path | 必填 | sensitive |
| `EVIDSIGHT_KNOWLEDGE_UPLOAD_MAX_BYTES` | Knowledge | int | `52428800` | public |
| `EVIDSIGHT_KNOWLEDGE_ALLOWED_EXTENSIONS` | Knowledge | csv enum | `pdf,docx,md,txt` | public |
| `EVIDSIGHT_KNOWLEDGE_DISK_PROTECTION_PERCENT` | Knowledge | int | `85`，范围 50—95 | public |
| `EVIDSIGHT_KNOWLEDGE_CLEAN_ENABLED` | Knowledge | bool | `true` | public |
| `EVIDSIGHT_KNOWLEDGE_CLEAN_STRIP_BOILERPLATE` | Knowledge | bool | `true` | public |
| `EVIDSIGHT_KNOWLEDGE_CLEAN_NORMALIZE_WHITESPACE` | Knowledge | bool | `true` | public |
| `EVIDSIGHT_KNOWLEDGE_CLEAN_REPAIR_UNICODE` | Knowledge | bool | `true` | public |
| `EVIDSIGHT_RESEARCH_LEASE_TTL_SECONDS` | Research | int | `120` | public |
| `EVIDSIGHT_RESEARCH_LEASE_RENEW_SECONDS` | Research | int | `30` | public |
| `EVIDSIGHT_RESEARCH_RECOVERY_SCAN_SECONDS` | Research | int | `60` | public |
| `EVIDSIGHT_RESEARCH_MAX_RUNNING_TASKS` | Research | int | `1`（2C2G） | public |
| `EVIDSIGHT_RESEARCH_MAX_QUEUED_TASKS` | Research | int | `20` | public |
| `EVIDSIGHT_RESEARCH_TASK_TIMEOUT_SECONDS` | Research | int | `3600` | public |
| `EVIDSIGHT_RESEARCH_WEB_CONTENT_TTL_SECONDS` | Research | int | `604800` | public |
| `EVIDSIGHT_RESEARCH_FAILED_REVISION_TTL_SECONDS` | Research | int | `2592000` | public |
| `EVIDSIGHT_PROVIDER_LLM_BASE_URL` | Provider | URL | 能力启用时必填 | sensitive |
| `EVIDSIGHT_PROVIDER_LLM_API_KEY` | Provider | string | 能力启用时必填 | secret |
| `EVIDSIGHT_PROVIDER_LLM_MODEL` | Provider | string | 能力启用时必填 | public |
| `EVIDSIGHT_PROVIDER_REQUEST_TIMEOUT_SECONDS` | Provider | int | `60` | public |
| `EVIDSIGHT_AUDIT_RETENTION_DAYS` | Platform | int | `365` | public |
| `EVIDSIGHT_TRACE_RETENTION_DAYS` | 服务各自 | int | `30` | public |
| `EVIDSIGHT_BACKUP_RETENTION_DAYS` | 运维 | int | `30` | public |
| `EVIDSIGHT_LOG_LEVEL` | 服务各自 | enum | `INFO` | public |
| `EVIDSIGHT_WEB_API_BASE_PATH` | Web | string | `/api/v1` | public |

生产部署可以覆盖默认值，但必须在变更记录中说明容量、安全和保留影响。新增键先进入本表，再进入 `.env.example`、Settings Schema、Compose 和配置测试。

Refresh Cookie 与 CSRF 传输规则见 [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md) §4.2；错误码见 [API.md](API.md) §5。生产环境 `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME` 必须使用 `__Host-` 前缀（同时要求 `Secure` 且不设 Domain）；`EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS` 用于 Refresh/Logout 的 Origin 白名单校验，为空时按同站处理。开发环境允许将 `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE` 置为 `false` 以便在 HTTP 下调试，但生产必须为 `true`。`EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` 开启后仅作为 M1 迁移期兼容入口，需记录不含 Token 的弃用调用量并在观测窗口归零后删除，禁止被新前端依赖。

Service JWT 只由 Research 签发、由 Knowledge 验证，使用独立于用户 Access/Refresh Token 的密钥材料。JWT Header 必须包含 `kid`；Payload 必须包含 `iss`、`aud`、`sub=research-service`、`token_type=service`、`jti`、`iat`、`nbf` 和 `exp`。Knowledge 只接受算法允许列表、配置的 Issuer、`knowledge-internal` Audience 和已登记 Key ID。公钥文件必须支持当前 Key 与上一 Key 的受控验证窗口；私钥、公钥内容和 Token 不得进入日志或错误响应。

> 备注：`services/knowledge/app/config.py` 沿用服务内无前缀命名（如 `CLEAN_ENABLED`、`CHUNK_SIZE`），运行时以服务内值为准；上表按 `EVIDSIGHT_KNOWLEDGE_` 命名空间登记同名键，作为部署与跨服务契约的规范名称。M2 数据清洗 4 键即按此约定登记。

## 4. 约束

- Research 续租周期必须小于租约时长的一半；Scanner 间隔不得大于租约时长；
- 单次不可中断操作超时必须短于剩余租约；
- Chat v1.0 不提供启用多 KB 的 Feature Flag；多选不能通过配置绕过权威规范；
- 外部 Provider 不作为 API 启动硬依赖，但能力不可用必须进入 readiness capability、错误和指标；
- `DEBUG` 不得改变权限、验签、正文外发或敏感日志边界。

## 5. 配置验证

M0 应提供统一配置 smoke，验证必需键、前缀隔离、URL、范围、队列、Redis DB 冲突、生产默认密钥和 Compose 注入完整性。错误输出只显示键名和安全原因，不回显值。
