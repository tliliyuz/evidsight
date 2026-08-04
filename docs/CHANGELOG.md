# Changelog

本文记录 EvidSight 产品规范、架构、契约和实现的可审查变化。格式参考 Keep a Changelog；“已确认设计”不等同于“已经实现或发布”。

## [Unreleased]

### Added

- 接受 ADR-007：Knowledge 文档版本化生命周期与删除一致性——每次入库/重处理创建独立 `document_version` 并以阶段 Checkpoint 为恢复点（MySQL 为唯一权威），Embedding 先入 staging、发布以 per-KB `index_status` 短时锁原子切换 `active_version` 并清理旧向量，删除走 KB `deleting` 幂等清理与 BM25 缓存失效；检索权限语义由 ADR-002/005 交叉引用覆盖，不重复定义；ADR 检查项 4、5 命中，负责人于 2026-08-04 接受为 `accepted`；同步 decisions 索引、RAG_PIPELINE §16 门禁记录、DATABASE §9 与 API §6.2 交叉引用。（2026-08-04）
- M1 退出门禁 6 负向日志测试补齐：新增 `services/knowledge/tests/unit/services/test_auth_service.py::TestLoginLogSensitivity`，断言登录成功与失败路径日志均不含密码明文、登录成功日志不含 Access/Refresh Token 明文；负向验证确认在 `auth_service.login` 注入密码日志时测试正确 RED，GREEN 无生产代码修改（目标行为由既有实现满足）；同步 TESTING.md §3.2 与 IDENTITY_AND_ACCESS ADR 检查记录。（2026-08-04）
- 补齐知识库权限矩阵验收测试：新增 `services/knowledge/tests/unit/core/test_permissions.py` 纯函数矩阵测试，以 PRD §8.2 五列矩阵驱动 `require_kb_readable`（READ 由 visibility 优先：public→所有登录用户、private→owner+admin）、`require_kb_writable`（WRITE 由 ownership 决定、admin 治理覆盖）与 `require_kb_owner`（上传文档 owner-only、admin 不可代传），共 15 个用例；容器内负向验证确认移除 admin 分支或破坏 owner 检查时对应测试正确 RED，GREEN 无生产代码修改（目标行为由既有 `permissions.py` 满足）；同步 TESTING.md §3.2 与 IDENTITY_AND_ACCESS ADR 检查记录。（2026-08-04）
- 补齐 IA-010 签名密钥轮换验收测试：`test_service_security.py` 新增 `TestServiceKeyRotation`，验证 Service JWT 双 Key 验证窗口内新旧 Token 均按 Key ID 通过、窗口后移除旧 Key 旧 Token 失效且新 Token 仍有效、切换签发侧使用新 Key ID 后按新 Key 验证通过；容器内负向验证确认测试可检测轮换窗口支持缺失，GREEN 无生产代码修改（目标行为由既有 `verify_service_token` 多 Key 映射满足）；同步 TESTING.md §3.2 与 IDENTITY_AND_ACCESS ADR 检查记录。（2026-08-04）
- 补齐 IA-005 禁用用户全链路 API 层验收测试：新增 `services/knowledge/tests/unit/api/test_disabled_user_access.py`，依赖层验证 `get_current_user` 对不存在/禁用用户统一抛 `E5010`，API 层验证禁用用户对 Chat 创建、单个/批量上传、重处理、治理写操作（禁用/启用用户、重置密码）均返回 401 `E5010` 且不进入业务逻辑；容器内负向验证确认测试可检测禁用检查缺失，GREEN 无生产代码修改（目标行为由既有 `get_current_user` 满足）；同步扩充 TESTING.md §3.2 与 IDENTITY_AND_ACCESS §13 IA-005 场景表述。（2026-08-04）
- 实现 Service JWT 基础设施与 Internal Identity Status Provider（IA-012）：Research 以 RS256 私钥签发服务身份 Token（`create_service_token`），Knowledge 以公钥验证（`verify_service_token`，Issuer/Audience/Key ID/时间窗口）；Knowledge 落地 `GET /internal/v1/identity/users/{id}/status` Provider 端点，按 API.md §11.1 顺序校验，返回契约 `IdentityStatusResponse`（1.0.0），错误统一使用 `error-response.schema.json` 信封；`users` 新增 `status_version` 列并在状态变更时递增；`auth_middleware` 豁免 `/internal/v1/*`；测试密钥动态生成，不提交仓库。（2026-08-04）
- 实现 Research 身份状态门禁（IA-012 身份状态契约 Research 侧）：新增 `app/core/identity_status_client.py`（`check_user_status`，调用 `GET /internal/v1/identity/users/{id}/status`，携带 Service JWT、Contract 版本、`X-Request-ID` 与 W3C `traceparent`）；`create_task` 创建任务前实时复核用户状态，用户禁用/不存在 → `UserDisabledException`（E1010/401）、身份库不可用/网络/超时/意外响应 → `ServiceUnavailableException`（E9002/503），失败关闭且不分发 Worker；新增配置键 `EVIDSIGHT_KNOWLEDGE_INTERNAL_BASE_URL` 与 `EVIDSIGHT_IDENTITY_STATUS_TIMEOUT_SECONDS`。（2026-08-04）
- 接受 ADR-006：Refresh Token 浏览器传输收口为 HttpOnly Cookie + double-submit CSRF，`login`/`refresh` 不再返回 Refresh Token 明文，`refresh`/`logout` 新增必需 `X-CSRF-Token`；旧 body `refresh_token` 仅作为配置开关控制的迁移期兼容入口。（2026-08-03）
- 实现事件③ Refresh Token Cookie/CSRF 收口后端切片（IA-015/IA-016）：新增 CSRF 基础设施与 Cookie 读写（`app/core/csrf.py`：`generate_csrf_token`/`verify_csrf` double-submit 校验与 Origin 白名单、`set_refresh_cookie`/`set_csrf_cookie`/`clear_auth_cookies`）及 7 个 `EVIDSIGHT_PLATFORM_*` 配置键；v1 登录/刷新/退出改用 HttpOnly Refresh Cookie + `X-CSRF-Token`（`login` 响应不含 `refresh_token` 明文并设置 Refresh/CSRF Cookie、`refresh` 从 Cookie 读取并原子轮换且同响应轮换 Cookie、`logout` 幂等撤销并清除 Cookie，刷新失败按 ADR-006 清除 Cookie）；`EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` 开启时允许 Refresh Cookie 缺失回退 body `refresh_token` 并记录不含 Token 的弃用日志。（2026-08-03）
- 实现事件③ Refresh Token Cookie/CSRF 收口前端切片（IA-015/IA-016）：`apps/web` 登录/刷新/退出切换至 v1 端点（`/api/v1/auth/login` 消费 unwrapped `LoginV1Response`；`/api/v1/auth/refresh` 与 `/api/v1/auth/logout` 从非 HttpOnly CSRF Cookie 读取并以 `X-CSRF-Token` Header 回传、不带 body `refresh_token`）；Axios 实例启用 `withCredentials` 携带凭据；前端不再读取/保存 Refresh Token 明文（移除 `localStorage.refresh_token` 读写与 Pinia `refreshToken` 状态，仅在清态时保留遗留键清理）；刷新失败（CSRF 缺失/不一致、Refresh Cookie 过期/吊销）统一按刷新失败处理清除 Access Token 与用户状态并返回登录入口。（2026-08-03）
- e01 外部 DTO 整数 ID 只读取证：分类 A 类用户 `id`（6 处改 UUID）、B 类外部响应用户引用（6 处移除内部 `users.id`）、C 类内部资源 ID（4 处保留 BIGINT）；为 DTO UUID 迁移事件的规范与验收提供输入。（2026-08-03）
- 落地 Internal Identity Status 契约最小可执行集合：`schemas/v1/`（common / identity-status-response / error-response）、Fixture（identity-status-response 1 valid + 12 invalid，error-response 2 valid + 3 invalid）、Pydantic 参考模型与 `loader.py`（`$ref` 文件系统解析 + `referencing.Registry`）、契约自检与 Knowledge Provider / Research Consumer 契约测试；Provider 端点 `GET /internal/v1/identity/users/{id}/status` 当前为正确 RED。（2026-08-03）
- 建立文档治理指南，统一实现偏离、实现领先、迁移态和权威文档冲突的取证、裁决、状态与退出门禁。（2026-08-03）
- 建立 EvidSight PRD、总体架构、身份与访问、API、Database、Knowledge/Research Pipeline、Frontend 和 UI 规范基线。（2026-08-01）
- 建立 Monorepo 迁移计划、开发指南、测试策略、配置、数据保留、运维及数据迁移回滚规范。（2026-08-01）
- 建立重要架构决策记录目录。（2026-08-01）
- 完成 DocMind 后端与前端、ResearchMind 后端的 M0 Monorepo 结构迁移，并保留可审查的来源提交与 Git 历史。（2026-08-02）
- 建立 M1 统一身份、服务认证与敏感数据外发策略 ADR 候选，进入 M1 规范与验收准备。（2026-08-02）
- 为 Knowledge 既有用户增加稳定 Platform User UUID，并将 Research Task 用户归属改为无跨库外键的 UUID。（2026-08-02）
- 为 Knowledge 入库流水线新增确定性 Clean 数据清洗阶段（页号/页眉页脚去噪、空白/空行规整、损坏 Unicode 修复），位于 Parse 与 Chunk 之间，由 `CLEAN_ENABLED` 与三个逐项开关控制，仅影响新入库内容；实现与单测见 `app/rag/cleaner.py`、`tests/unit/rag/test_cleaner.py`。（2026-08-02）

### Updated

- M1 收尾并标记完成：六条退出门禁逐条核对证据齐备（双侧 JWT Claims/过期/禁用语义测试一致、禁用用户全链路拒绝、服务间伪造拒绝、KB 权限矩阵、Contract Provider/Consumer 测试、敏感信息不进前端响应或普通日志），ROADMAP 将 M1 状态由"进行中"更新为"已完成"并勾选全部门禁清单，DEVELOPMENT.md 当前阶段同步；Retrieval/Evidence Contract 与 IA-006—IA-009 依赖 Internal Retrieval，明确划入 M2/M3。（2026-08-04）
- 固化 M1 Refresh Token Cookie/CSRF 安全收口规范：浏览器目标态使用 HttpOnly Refresh Cookie + double-submit CSRF，Refresh/Logout 先校验 CSRF/Origin，旧 body `refresh_token` 仅作为迁移期兼容入口。（2026-08-03）
- 固化外部 User DTO UUID 与遗留 Auth 接口退出规则：`/api/v1/auth/*` 的 User DTO `id` 一律为 Platform User UUID，旧 `/api/auth/*` 与旧 `id=int` UserResponse 仅作为 M1 迁移期兼容并需调用量观测后删除。（2026-08-03）
- 实现 IA-013/IA-014 事件②：Access Token 移除 `username` 等可派生展示 Claim，前端身份权威来源改为 `GET /api/v1/auth/me`（`UserSummary`，`id` 为 Platform User UUID 字符串，`username`/`role`/`status` 来自数据库当前状态）；登录、重载、Refresh 均经 `/me` 重建身份，`isLoggedIn` 在 `/me` 完成前保持未就绪，客户端不再解析 JWT Claim 或恢复持久化 `user`。（2026-08-03）
- 落地事件①外部 User DTO UUID 化（IA-017）：`/api/v1/auth/register` 返回 `UserSummary`（`id` 为 Platform User UUID），旧 `/api/auth/register` 保留 `UserResponse(id=int)` 迁移期兼容；admin 用户 DTO 与 `{user_id}` 路由参数改 Platform User UUID；B 类外部响应用户引用全部移除内部 `users.id`（`KnowledgeBaseResponse`/`PublicKnowledgeBaseResponse` 用 `owner`，`AdminKBItem`/`ConversationResponse`/`TraceListItem`/`TraceDetailResponse` 用 `owner_user_id`，`AdminDocItem` 用 `owner_id`）；前端 KnowledgeDetail isOwner、admin TraceList/TraceDetail/KnowledgeList 视图同步对齐 `owner`/`owner_user_id` 展示与跳转。（2026-08-03）
- 固化 M1 Internal Identity Status 公共契约：Research 创建长期任务前通过独立 Service JWT 向 Knowledge 实时复核用户状态，身份事实源不可用时失败关闭。（2026-08-03）
- 实现 IA-004 Refresh Token 重放响应：已轮换 Token 再次出现时原子撤销所属 Family，持久化不含 Token 的身份安全审计事件并返回 `E5009`。（2026-08-02）
- 实现 IA-003/IA-011 Refresh Token 原子轮换：Knowledge 登录创建 Platform User UUID 归属的 Token Family，刷新锁定旧 Token、记录唯一后继并阻止并发双花。（2026-08-02）
- 移除 Research 本地注册、登录、刷新与密码管理能力及 `users`、`refresh_tokens` 表；Research 仅验证 Knowledge 签发的 Access Token，并以外部 Platform User UUID 保存任务归属。（2026-08-02）
- 实现 IA-001/IA-002 首个纵向切片：Access Token 补齐 issuer、双 Audience、UUID subject、类型、JWT ID 和时间 Claim，Knowledge 与 Research 分别校验自身 Audience。（2026-08-02）
- 明确统一 Access Token 使用双 Audience 数组，Knowledge 与 Research 分别配置并验证自身 Audience；补充 IA-001/IA-002 可执行验收映射。（2026-08-02）
- 接受 ADR-005，解除 M1 验收测试设计门禁并进入首个纵向切片确认阶段。（2026-08-02）
- 建立 ADR 二元触发检查、负责人明确裁决、豁免留痕和既有决策替代门禁，并将其接入 SDD 入口。（2026-08-02）
- 统一 M0 已完成、M1 准备中的阶段状态；根据负责人裁决移除已删除 `docs/migration/` 过程记录的门禁和失效引用。（2026-08-02）
- 将项目级文档分为 `specs/`、`guides/`、`plans/`、`decisions/` 与迁移证据层，并新增文档中心和权威规范索引；模块专项文档继续跟随模块维护。（2026-08-01）
- 明确 v1.0 Chat 只绑定单个知识库；前端保留可演进选择器，但多选不可执行并提示“多知识库问答规划中”。（2026-08-01）
- 多 KB 能力仅用于 Research 通过权限感知的 Internal Retrieval 检索；多 KB Chat 延后至 v1.x。（2026-08-01）
- 统一 Research 七阶段顺序为 Planning → Searching → Fetching → Reranking → Synthesizing → Evidence Graph Build → Rendering。（2026-08-01）
- Internal Evidence 身份增加稳定 `document_version_id`，用于重处理后的历史来源追溯。（2026-08-01）
- 明确 M0 保留 Vue 来源迁移基线，M4 按前端专项规范交付唯一 React + TypeScript Web。（2026-08-01）
- 将 LLM、Embedding、Rerank 与 Tavily 的 Base URL 和模型配置从根目录 `.env` 透传到对应服务容器，并清理未接线的示例变量。（2026-08-02）
- Knowledge 离线检索评估 `eval_retrieval.py` 在指标未达标时以非零码退出，使 Rec@5 成为可重复 fail-fast 门禁（用于清洗前后度量）。（2026-08-02）

### Fixed

- 修复 Research API 将任务投递到旧默认队列 `research_task`、而 Worker 仅监听 `research.execute` 导致任务未被拾取的问题；同时将定时任务显式路由到 `research.periodic`。（2026-08-02）
- 修复 Nginx 将旧 Research 任务路由 `/api/research` 错误转发到 Knowledge 或改写为 `/api/` 的问题；任务路径现原样代理，并保留命名空间下的 Research 健康检查与迁移期认证入口。（2026-08-02）
- 修复 Knowledge Celery 任务误投默认队列的问题，显式路由入库与删除任务；文档状态轮询增加请求防重叠及 429 限流退避。（2026-08-02）
- 移除无生产者的死队列 `research.recovery`（恢复任务继续投递到 `research.execute`），并统一队列配置键为 `CELERY_*` 惯例：补齐 `CELERY_PERIODIC_QUEUE`，Knowledge 队列改为 `CELERY_INGEST_QUEUE`/`CELERY_DELETE_QUEUE`，配置文档同步对齐。（2026-08-02）

### Refactored

（仅记录外部行为不变、内部结构/设计整理的重构；当前无此类条目。）

### Not Yet Implemented

- External OpenAPI、Internal Contract JSON Schema、Fixture 和生成物尚未落地。（2026-08-01）
- 本条目不声明统一身份、Internal Retrieval、Research 前端并入统一 Web、生产数据迁移或 v1.0 发布验收已经完成。（2026-08-02）

## 维护规则

- 行为、权限、状态机、公共契约和数据生命周期变化必须在同一变更中更新本文件。
- 变更分类与提交 subject 前缀对齐：`add`→`### Added`、`update`→`### Updated`、`fixed`→`### Fixed`、`refactor`→`### Refactored`；纯重构（外部行为不变、仅内部结构整理）必须记录在 `### Refactored` 下。
- `[Unreleased]` 下每个一级变更条目必须标注实际改动日期，格式为 `（YYYY-MM-DD）`；不得只依赖版本发布日期。
- 只记录实际合并的事实；测试结果必须保留实际命令、环境、日期和结果，不以计划目标代替执行记录。
- 发布版本使用 `MAJOR.MINOR.PATCH`，并标注日期、迁移要求、兼容窗口和已知限制。
