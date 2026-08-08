# CONFIGURATION — 配置规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 配置基线 |
| 最后更新 | 2026-08-06 |

## 1. 规则

- 每个配置键必须声明所有者、类型、必填性、默认值和安全级别；
- 生产密钥不得提供可用默认值；
- 未知键告警，类型或边界错误使启动/配置 smoke 失败；
- `.env.example` 只放键名和安全示例，不放真实凭证；
- 两个服务不得读取对方私有配置命名空间。

## 2. 命名空间

键名以各服务 `config.py` 实际读取为准：跨服务身份/契约键使用 `EVIDSIGHT_*` 前缀；服务内部键（数据库、Redis、队列、上传/向量、Provider、令牌签名、数据清洗）使用服务内无前缀命名，按服务归属，由对应服务容器注入同名环境变量。

| 命名空间 | 所有者 | 职责 |
|:---|:---|:---|
| `EVIDSIGHT_PLATFORM_*` | 统一身份/平台 | JWT issuer/audience、Refresh Cookie/CSRF、Service JWT、内部契约超时 |
| `EVIDSIGHT_KNOWLEDGE_*` / `EVIDSIGHT_RESEARCH_*` | 对应服务 | 跨服务契约键（Audience、Service JWT 密钥材料、Knowledge 内部 API 基址） |
| 服务内无前缀键（`MYSQL_*`、`REDIS_URL`、`CELERY_*`、`UPLOAD_DIR`、`CHROMA_PERSIST_DIR`、`LLM_*`、`EMBEDDING_*`、`RERANK_*`、`TAVILY_*`、`JWT_SECRET_KEY`、`CLEAN_*` 等） | 对应服务 | 服务内部数据库、Redis、队列、文件/向量、Provider、令牌签名与数据清洗 |

同名无前缀键在不同服务容器中取值各自独立，互不共享；两个服务不得读取对方私有配置命名空间。

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

本表只登记实现真实读取的键（以两服务 `config.py` 为准）；未实现的规划键见表后说明，不在注册表中登记。

**身份与跨服务契约键**

| 键 | 所有者 | 类型 | 必填/默认值 | 安全级别 |
|:---|:---|:---|:---|:---|
| `EVIDSIGHT_PLATFORM_JWT_ISSUER` | Platform | string | 必填 | public |
| `EVIDSIGHT_PLATFORM_JWT_AUDIENCES` | Platform | csv string | `evidsight-knowledge,evidsight-research` | public |
| `EVIDSIGHT_KNOWLEDGE_JWT_AUDIENCE` | Knowledge | string | `evidsight-knowledge` | public |
| `EVIDSIGHT_RESEARCH_JWT_AUDIENCE` | Research | string | `evidsight-research` | public |
| `JWT_SECRET_KEY` | Knowledge/Research | string | 必填（用户 Access/Refresh Token 签名，生产不得提供默认值） | secret |
| `REFRESH_TOKEN_SECRET_KEY` | Knowledge/Research | string | 默认回退 `JWT_SECRET_KEY` | secret |
| `JWT_ALGORITHM` | Knowledge/Research | enum | `HS256` | public |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Knowledge/Research | int | `15` | public |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Knowledge/Research | int | `7` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME` | Platform | string | `__Host-evidsight_refresh` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH` | Platform | string | `/`（`__Host-` 前缀强制 Path=/，RFC 6265bis §5.5） | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE` | Platform | bool | `true` | public |
| `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE` | Platform | enum | `lax`；跨站部署用 `none` 且必须 `Secure` | public |
| `EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME` | Platform | string | `evidsight_csrf` | public |
| `EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS` | Platform | csv string | 生产必填，为空拒绝启动（严格 Origin 校验） | public |
| `EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` | Platform | bool | `false`（M1 迁移期可开） | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER` | Platform | string | `evidsight-platform` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_ALGORITHM` | Platform | enum | `RS256` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE` | Platform | string | `knowledge-internal` | public |
| `EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS` | Platform | int | `60`，范围 10—300（compose 开发默认 `300`） | public |
| `EVIDSIGHT_RESEARCH_SERVICE_JWT_ACTIVE_KID` | Research | string | 必填（compose 开发默认 `dev-20260805`） | public |
| `EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE` | Research | path | 必填 | secret |
| `EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE` | Knowledge | path | 必填 | sensitive |
| `EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL` | Research | URL | 必填（Knowledge 内部 API 基址，如 `http://knowledge-api:8000`，必须直达内部网络，不得走 Nginx） | secret |
| `EVIDSIGHT_IDENTITY_STATUS_TIMEOUT_SECONDS` | Research | float | `5.0`，范围 0&lt;x≤30 | public |
| `EVIDSIGHT_INTERNAL_RETRIEVAL_TIMEOUT_SECONDS` | Research | float | `10.0`，范围 0&lt;x≤60 | public |
| `EVIDSIGHT_INTERNAL_RETRIEVAL_RETRY_MAX` | Research | int | `2`，范围 0—5（可重试的瞬时不可用错误重试上限） | public |

**服务内部键（按服务归属）**

| 键 | 所有者 | 类型 | 必填/默认值 | 安全级别 |
|:---|:---|:---|:---|:---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_DATABASE` | 服务各自（`MYSQL_DATABASE` 分别为 `knowledge_db` / `research_db`） | string/int/string | 必填 | public |
| `MYSQL_PASSWORD` | 服务各自 | string | 必填 | secret |
| `REDIS_URL` | 服务各自 | URL | 必填（Knowledge 默认 `redis://redis:6379/0`、Research `redis://redis:6379/3`，独立 Redis DB） | secret |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | 服务各自 | URL | 必填（独立 Redis DB，两服务不同库） | secret |
| `CELERY_INGEST_QUEUE` | Knowledge | string | `knowledge.ingest` | public |
| `CELERY_DELETE_QUEUE` | Knowledge | string | `knowledge.delete` | public |
| `CELERY_EXECUTE_QUEUE` | Research | string | `research.execute` | public |
| `CELERY_PERIODIC_QUEUE` | Research | string | `research.periodic` | public |
| `UPLOAD_DIR` | Knowledge | path | 必填 | sensitive |
| `UPLOAD_MAX_SIZE` | Knowledge | int | `52428800` | public |
| `ALLOWED_EXTENSIONS` | Knowledge | csv enum | `pdf,docx,md,txt` | public |
| `CHROMA_PERSIST_DIR` | Knowledge | path | 必填 | sensitive |
| `CLEAN_ENABLED` | Knowledge | bool | `true` | public |
| `CLEAN_STRIP_BOILERPLATE` | Knowledge | bool | `true` | public |
| `CLEAN_NORMALIZE_WHITESPACE` | Knowledge | bool | `true` | public |
| `CLEAN_REPAIR_UNICODE` | Knowledge | bool | `true` | public |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_FLASH_MODEL` | 服务各自 | URL/string/string | 能力启用时必填（`LLM_FLASH_MODEL` 两服务默认不同） | public |
| `LLM_API_KEY` | 服务各自 | string | 能力启用时必填 | secret |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | Knowledge | URL/string | 能力启用时必填 | public |
| `EMBEDDING_API_KEY` | Knowledge | string | 能力启用时必填 | secret |
| `RERANK_BASE_URL` / `RERANK_MODEL` | Knowledge | URL/string | 能力启用时必填 | public |
| `RERANK_API_KEY` | Knowledge | string | 能力启用时必填 | secret |
| `TAVILY_BASE_URL` | Research | URL | `https://api.tavily.com` | public |
| `TAVILY_API_KEY` | Research | string | 能力启用时必填 | secret |
| `BUDGET_MAX_SUB_QUESTIONS` | Research | int | `5`（RESEARCH_PIPELINE §14 服务端默认推导上限） | public |
| `BUDGET_MAX_LLM_TOKENS` | Research | int | `100000` | public |
| `BUDGET_MAX_PROVIDER_CALLS` | Research | int | `60` | public |
| `BUDGET_MAX_COST_USD` | Research | float | `1.0` | public |
| `BUDGET_DEADLINE_SECONDS` | Research | int | `3600`（总时限） | public |
| `RESEARCH_TASK_LEASE_TTL_SECONDS` | Research | int | `300`（DB 租约时长，RESEARCH_PIPELINE §13.1） | public |
| `RESEARCH_TASK_LEASE_RENEW_INTERVAL` | Research | int | `60`（续租周期，必须 < 租约时长 / 2，§13.1） | public |
| `RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS` | Research | int | `60`（Recovery Scanner 周期，必须 ≤ 租约时长，§13.1） | public |
| `PENDING_REDELIVERY_THRESHOLD_SECONDS` | Research | int | `300`（pending 重投递阈值，§13.6） | public |
| `PENDING_REDELIVERY_MAX_RETRIES` | Research | int | `3`（最大重投次数，超限后受控失败 E3118，§13.6） | public |

**规划键（目标态，未实现，暂不登记）**

以下键被 DATA_RETENTION / OPERATIONS / RESEARCH_PIPELINE 引用，但当前实现尚未读取，属目标态规划；实现落地后再按「新增键」流程登记，落地前不作为部署必填：磁盘保护水位（`EVIDSIGHT_KNOWLEDGE_DISK_PROTECTION_PERCENT`）、Web 正文保留（`EVIDSIGHT_RESEARCH_WEB_CONTENT_TTL_SECONDS`）、失败 Revision 保留（`EVIDSIGHT_RESEARCH_FAILED_REVISION_TTL_SECONDS`）、审计/Trace 保留（`EVIDSIGHT_AUDIT_RETENTION_DAYS`、`EVIDSIGHT_TRACE_RETENTION_DAYS`）、日志级别与 Web 基础路径等。

生产部署可以覆盖默认值，但必须在变更记录中说明容量、安全和保留影响。新增键（仅登记实现真实读取的键）先进入本表，再进入 `.env.example`、Settings Schema、Compose 和配置测试；未实现键不登记。

Refresh Cookie 与 CSRF 传输规则见 [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md) §4.2；错误码见 [API.md](API.md) §5。生产环境 `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME` 必须使用 `__Host-` 前缀（同时要求 `Secure` 且不设 Domain）；`EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS` 用于 Refresh/Logout 的 Origin 白名单校验，生产环境必填、为空拒绝启动（fail-fast，避免带病上线后服务间认证与 CSRF 校验全部失效）；开发环境允许为空按同站处理。开发环境允许将 `EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE` 置为 `false` 以便在 HTTP 下调试，但生产必须为 `true`。`EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` 开启后仅作为 M1 迁移期兼容入口，需记录不含 Token 的弃用调用量并在观测窗口归零后删除，禁止被新前端依赖。

Service JWT 只由 Research 签发、由 Knowledge 验证，使用独立于用户 Access/Refresh Token 的密钥材料。JWT Header 必须包含 `kid`；Payload 必须包含 `iss`、`aud`、`sub=research-service`、`token_type=service`、`jti`、`iat`、`nbf` 和 `exp`。Knowledge 只接受算法允许列表、配置的 Issuer、`knowledge-internal` Audience 和已登记 Key ID。公钥文件必须支持当前 Key 与上一 Key 的受控验证窗口；私钥、公钥内容和 Token 不得进入日志或错误响应。

> 键名以 `config.py` 实际读取为准：跨服务身份/契约键使用 `EVIDSIGHT_*` 前缀，服务内部键使用无前缀命名（见 §2）。本注册表只登记实现真实读取的键；规划键不登记，待实现落地后再登记。
> ADR 检查（2026-08-06）：命中第 7 项（跨规范影响）。负责人豁免 ADR——配置键命名收敛不改变安全基线、外部契约或服务边界，属文档/部署资产一致性整理；记录见 [CHANGELOG](../CHANGELOG.md)。

## 4. 约束

- Research 续租周期必须小于租约时长的一半；Scanner 间隔不得大于租约时长；
- 单次不可中断操作超时必须短于剩余租约；
- Chat v1.0 不提供启用多 KB 的 Feature Flag；多选不能通过配置绕过权威规范；
- 外部 Provider 不作为 API 启动硬依赖，但能力不可用必须进入 readiness capability、错误和指标；
- `DEBUG` 不得改变权限、验签、正文外发或敏感日志边界。

## 5. 配置验证

M0 应提供统一配置 smoke，验证必需键、前缀隔离、URL、范围、队列、Redis DB 冲突、生产默认密钥和 Compose 注入完整性。错误输出只显示键名和安全原因，不回显值。
