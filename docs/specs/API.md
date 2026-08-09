# 据见（EvidSight）API 与事件协议

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认规范 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-08-09 |

> 本文是外部/内部 HTTP、错误语义和 SSE 的权威规范。产品行为见 [PRD.md](PRD.md)，身份与授权见 [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md)，服务边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。跨服务字段 Schema 由 [`packages/contracts/`](../../packages/contracts/README.md) 定义；本文不复制 ORM、数据库或 Pipeline 内部结构。

M1 的统一身份、服务认证和敏感数据外发决策由已接受的 [ADR-005](../decisions/ADR-005-unified-identity-service-auth-egress.md) 裁决。现在可以从本文导出验收测试；生产实现仍须先观察对应验收测试因目标行为缺失而正确 RED。

## 1. 目标与边界

本规范统一 Web、Knowledge Service、Research Service 和 Internal Retrieval 的协议表面，使客户端、Provider、Consumer 和测试能够独立演进。

- 外部正式接口：`/api/v1/*`；
- 内部接口：`/internal/v1/*`，不得由 Nginx 对外暴露；
- Chat SSE 与 Research SSE 使用独立业务协议；
- v1.0 未实现的 P1 接口只声明预留边界，不伪装为已上线。

## 2. 协议与版本

- HTTP 使用 HTTPS；JSON 与 SSE 均为 UTF-8。
- 时间使用 RFC 3339 UTC（推荐 `Z`）；持续时间使用毫秒整数。
- ID 对外为不透明 UUID 字符串，客户端不得依赖排序或内部主键。所有外部 User DTO 的 `id` 必须是 Platform User UUID；Knowledge 迁移期内部 `users.id` BIGINT 不得出现在 `/api/v1/*` 响应、SSE 事件或前端状态中。
- 外部 `/api/v1` 的 Breaking Change 使用新主版本；新增可选字段或非终态枚举值必须允许旧客户端安全降级。
- Internal Retrieval 使用精确 Contract 版本和 `additionalProperties: false`；其未知字段/枚举必须拒绝，不适用外部客户端的宽容读取规则。
- 迁移期旧 DocMind/ResearchMind 路由保持原行为，由兼容层映射；废弃前必须有调用方清单、替代路径、观测窗口和回归测试。

## 3. 通用请求约定

| 项目 | 约定 |
|:---|:---|
| 用户认证 | `Authorization: Bearer <access-token>`，语义引用身份规范 |
| 请求关联 | `X-Request-ID`；缺失时网关生成，跨服务继续传播 |
| 幂等创建 | 可重试创建请求使用 `Idempotency-Key`，同用户同端点同 Key 必须返回同一结果；不同载荷返回 `409` |
| 分页 | `page` 默认 1；`page_size` 默认 20、最大 100 |
| 排序 | `sort_by` 只能取端点允许列表；`order=asc|desc` |
| 条件更新 | 支持资源版本时使用 `If-Match`；版本冲突返回 `409` |

未知请求字段默认由 Schema 拒绝。查询筛选、排序字段和上传大小必须使用允许列表；不得把客户端字段直接拼接到 SQL、文件路径或 Provider 请求。

### 3.1 外部 DTO 最小基线

`docs/openapi/evidsight-v1.yaml` 是字段、类型和约束的唯一权威源；本文只定义行为、权限、状态码与兼容语义，不再重复 Schema。下表仅保留 OpenAPI 尚未覆盖 DTO 的最小基线；已由 OpenAPI 覆盖的 Knowledge Base / Document / Conversation 字段契约一律以 `docs/openapi/evidsight-v1.yaml` 为准（实际字段名如 `uuid`/`kb_uuid`/`segment_id` 与 OpenAPI 定义一致，不以此表为准）。

| DTO | 必需字段 | 关键约束 |
|:---|:---|:---|
| `LoginRequest` | `username`、`password` | 非空；错误不区分账号不存在和密码错误 |
| `UserSummary` | `id`、`username`、`role`、`status` | `id` 为 Platform User UUID，不是 Knowledge 内部 `users.id`；`role=user|admin`，`status=active|disabled` |
| `KnowledgeBaseCreate` / `KnowledgeBaseResponse` / `KnowledgeBaseList` | 见 `docs/openapi/evidsight-v1.yaml` | `visibility=private|public`；`owner` 为 Platform User UUID |
| `DocumentResponse` / `DocumentList` / `DocumentUpload` / `DocumentChunk` / `DocumentLocation` | 见 `docs/openapi/evidsight-v1.yaml` | `status=queued|processing|completed|partial|failed|deleting`；分块 `segment_id` 为稳定身份，`id` 仅迁移期兼容 |
| `ConversationResponse` / `ConversationDetail` / `ConversationList` | 见 `docs/openapi/evidsight-v1.yaml` | 会话只属于一个用户和一个 KB；`knowledge_base_id` 用于创建请求 |
| `ChatStreamRequest` | `conversation_id`、`knowledge_base_id`、`message` | v1.0 只有单数 KB；消息非空 |
| `ResearchTaskCreate` | `topic`、`task_type`、`source_strategy`、`knowledge_base_ids`、预算摘要 | knowledge/hybrid 为 1—50 个 KB；web 必须为空 |
| `ResearchTaskResponse` | `id`、`status`、`phase`、`progress`、`recoverable`、时间 | 状态和 Phase 引用 Research Pipeline |
| `EvidenceResponse` | Contract `EvidenceReference` 的公开投影 | Internal 不含正文；展开时实时鉴权 |
| `ReportResponse` | `id`、`task_id`、`revision`、`status`、章节、引用、完整度摘要 | published Revision 不可变 |

正式 Schema 还必须定义分页对象、条件更新版本、上传 multipart、错误 `details` 白名单以及 Chat/Research SSE 每种 `data` 对象。

## 4. 通用响应与错误

单资源成功响应直接返回资源对象；列表统一返回：

```json
{"items": [], "page": 1, "page_size": 20, "total": 0}
```

状态码：同步创建 `201`，异步接受 `202`，成功读取/更新 `200`，无正文删除 `204`。

错误结构固定为：

```json
{
  "error": {
    "error_code": "RS_TASK_CONCURRENCY_LIMIT",
    "message": "当前运行中的研究任务已达到上限，请稍后重试。",
    "request_id": "01J...",
    "retryable": true,
    "details": {}
  }
}
```

错误命名空间为 `AUTH_*`、`KB_*`、`DOC_*`、`CHAT_*`、`RS_*`、`EVIDENCE_*`、`REPORT_*`、`INTERNAL_*`、`SYSTEM_*`。常用映射：校验 `400/422`，未认证 `401`，无权限 `403`，不可见/不存在 `404`，状态或幂等冲突 `409`，过大 `413`，限流/并发上限 `429`，内部错误 `500`，上游错误 `502/504`，依赖不可用 `503`。

`details` 只含安全、结构化、可操作信息。响应不得包含正文、密码、Token、服务凭证、SQL、内部路径或堆栈。

## 5. Auth API

| 方法与路径 | 权限 | 成功 | 主要语义 |
|:---|:---|:---:|:---|
| `POST /api/v1/auth/register` | 匿名、限流 | 201 | 创建用户并返回外部 User DTO |
| `POST /api/v1/auth/login` | 匿名、限流 | 200 | 登录并建立 Refresh Family |
| `POST /api/v1/auth/refresh` | Refresh Cookie + CSRF | 200 | 原子轮换；重放撤销 Family |
| `POST /api/v1/auth/logout` | Access Token + Refresh Cookie + CSRF | 204 | 幂等撤销并清理 Cookie |
| `GET /api/v1/auth/me` | 用户 | 200 | 返回最小用户与角色摘要 |
| `PUT /api/v1/auth/password` | 用户 | 204 | 改密并撤销全部 Refresh Family |

认证、轮换、禁用、Cookie/CSRF 和安全错误以身份规范为准。

浏览器 Auth API 的 Refresh Token 目标态只通过 Knowledge 设置的 HttpOnly Refresh Cookie 传输；`login` 和 `refresh` 响应体返回 Access Token，不返回 Refresh Token 明文。`refresh` 与 `logout` 请求必须携带 CSRF Cookie 对应的 `X-CSRF-Token` Header；CSRF 或 Origin 校验失败返回认证错误，且不得进入 Refresh Token 轮换、撤销或重放审计分支。

旧 `/api/auth/*` 路由、JSON Body `refresh_token` 和返回 `id=int` 的旧 User DTO 只作为 M1 迁移期兼容入口。兼容入口不得成为新前端契约，必须记录不含 Token 的弃用调用量，并在观测窗口归零、Web 与脚本 Consumer 全部切换到 `/api/v1/auth/*` 且回归测试通过后删除。迁移期文档必须同时标注目标路径、Consumer、观测方式和删除动作。

## 6. Knowledge API

### 6.1 Knowledge Base

| 方法与路径 | 权限 | 成功 |
|:---|:---|:---:|
| `POST /api/v1/knowledge-bases` | 用户 | 201 |
| `GET /api/v1/knowledge-bases` | 当前可见范围 | 200 |
| `GET /api/v1/knowledge-bases/{kb_id}` | READ | 200 |
| `PATCH /api/v1/knowledge-bases/{kb_id}` | owner；admin 治理字段 | 200 |
| `DELETE /api/v1/knowledge-bases/{kb_id}` | owner/admin 治理 | 204 |

READ、owner 和 admin 治理分别判断，权限矩阵引用 PRD §8。

`GET /api/v1/knowledge-bases` 必须以一个分页集合返回当前用户可见的知识库，并提供 FRONTEND §5.3 定义的「全部、我创建的、组织公开」范围筛选与名称搜索；同一知识库在可见范围并集中只能出现一次。查询字段与分页响应 Schema 由 `docs/openapi/evidsight-v1.yaml` 定义，React Consumer 只消费该 OpenAPI 契约，不得绑定 legacy DTO。

**Knowledge Base 外部 API 迁移态（2026-08-09）**：`/api/v1/knowledge-bases/*` 的 CRUD（POST 201 / GET 统一可见列表 / GET 详情 / PATCH 部分更新 / DELETE 204）与单一可见列表（`scope=all|mine|public` + `q` 名称搜索、分页去重、admin 治理可见）已实现，字段契约以 `docs/openapi/evidsight-v1.yaml` 为唯一权威。legacy `/api/knowledge-bases/*` 只作为兼容入口保留（更新使用 `PUT`、删除返回 `202`，mine 与 public 为两个独立分页端点且不支持名称搜索），按 API.md §15 观测调用量，仓库内 Consumer 迁移且观测窗口归零后由负责人确认删除。状态与解除门禁见 [ROADMAP](../plans/ROADMAP.md) M2/M4；ADR 检查 1–8：否（让实现回到既有 API.md §6.1 目标态，不改变权限模型、服务边界或数据生命周期）。

### 6.2 Document 与来源

| 方法与路径 | 权限 | 成功 | 说明 |
|:---|:---|:---:|:---|
| `POST /api/v1/knowledge-bases/{kb_id}/documents` | owner | 202 | 提交事务后分发入库 |
| `GET /api/v1/knowledge-bases/{kb_id}/documents` | KB READ | 200 | 是否展示分块受权限约束 |
| `GET /api/v1/documents/{document_id}` | KB READ | 200 | 返回状态与安全元数据 |
| `GET /api/v1/documents/{document_id}/chunks` | KB READ | 200 | 分页返回安全预览与稳定 `segment_id` |
| `POST /api/v1/documents/{document_id}/retry` | owner | 202 | 仅允许可重试状态，幂等 |
| `DELETE /api/v1/documents/{document_id}` | owner/admin 治理 | 204 | 异步清理另有状态字段 |
| `GET /api/v1/documents/{document_id}/locations/{location_id}` | 当前 READ | 200 | 实时鉴权后返回最小片段和定位 |

`location_id` 即 Segment 稳定 UUID（`chunks.segment_uuid`）。每次展开原文都按当前用户状态、KB 状态和 READ 权限重新鉴权（IDENTITY_AND_ACCESS §9）；权限撤销、文档删除或来源失效返回明确受限/不可用状态（迁移期 `E2015`）。成功响应为信封 `{"code","message","data"}`，`data` 含 `document_id`/`segment_id`/`minimal_excerpt`/`location`（`page_number` 或 `section_path`）/`source_updated_at`；`minimal_excerpt` 为临时内容，客户端不得持久化。

**Document 外部 API 迁移态（2026-08-09）**：本节 v1 端点已全部实现 —— 上传 `POST /api/v1/knowledge-bases/{kb_id}/documents`（202）、列表（200）、详情 `GET /api/v1/documents/{document_id}`（200）、分块列表（200，含稳定 `segment_id`）、重新处理 `POST /api/v1/documents/{document_id}/retry`（202，幂等）、删除 `DELETE /api/v1/documents/{document_id}`（204）与 location（实时鉴权），字段契约以 `docs/openapi/evidsight-v1.yaml` 为唯一权威。legacy `/api/knowledge-bases/{kb_id}/documents/*` 只作为兼容入口保留（单文件上传返回 `201`、重新处理路径名为 `reprocess`、删除返回 `202`），按 API.md §15 保留观测和退出门禁。状态与解除门禁见 [ROADMAP](../plans/ROADMAP.md) M2/M4；ADR 检查 1–8：否（让实现回到既有 API.md §6.2 目标态，不改变权限模型、服务边界或数据生命周期）。

**Chunk 列表迁移态（2026-08-09）**：分块列表 `GET /api/knowledge-bases/{kb_uuid}/documents/{doc_uuid}/chunks` 响应 items 新增 `segment_id`（映射 `chunks.segment_uuid`，即本节 location 端点的 `location_id`），同时保留旧 `id`（内部整数 PK）字段兼容。`segment_id` 是稳定 Segment ID 契约，前端必须使用它调用本节 location 端点；内部整数 `id` 不作为契约，仅迁移期兼容保留，在观测归零且 Consumer 全部切换后经负责人确认删除（DATABASE.md §5.5「Internal Retrieval 绝不返回 `id`」约束不涉及该管理视图的迁移期字段，location 检索路径始终只返回 `segment_id`）。Consumer 为 React 知识中心切片抽屉（FRONTEND §5.4）；观测方式为后端访问日志按响应字段消费分布，退出门禁为旧 `id` 字段消费归零且前端全量使用 `segment_id`。负责人于 2026-08-09 裁决「增补保留 id」；ADR 检查 1–8：否（向后兼容字段扩展并保留旧字段，暴露 DATABASE.md §5.5 既有稳定 Segment ID，不改变权限模型、服务边界或数据生命周期；裁决记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-09））。

文档状态为 `queued|processing|completed|partial|failed|deleting`（6 值，对齐 ADR-007 与 DATABASE.md §5.2；`deleting` 为异步删除过渡态）。只有满足 Pipeline 有效来源条件的文档可参与检索。文档版本化生命周期与删除一致性决策见 [ADR-007](../decisions/ADR-007-knowledge-document-lifecycle-delete-consistency.md) 与 [RAG_PIPELINE.md](../../services/knowledge/docs/RAG_PIPELINE.md)。

## 7. Chat 与 Conversation API

| 方法与路径 | 权限 | 成功 |
|:---|:---|:---:|
| `POST /api/v1/chat/stream` | 单个所选 KB READ | 200 SSE |
| `POST /api/v1/chat/generations/{generation_id}/cancel` | 创建者 | 202 |
| `GET /api/v1/conversations` | owner | 200 |
| `GET /api/v1/conversations/{conversation_id}` | owner | 200 |
| `PATCH /api/v1/conversations/{conversation_id}` | owner | 200 |
| `DELETE /api/v1/conversations/{conversation_id}` | owner | 204 |

v1.0 Chat 请求只接受一个 `knowledge_base_id`，Conversation 也只绑定一个 KB。每次问答实时校验该 KB；多轮上下文不得扩展到其他或已撤权 KB。多 KB Chat 属于 v1.x 规划能力，不得由客户端并发请求模拟。取消命令幂等，SSE 断开也可终止当前生成。检索或生成失败不得发送成功终态或伪造答案。

**Conversation 外部 API 迁移态（2026-08-09）**：`/api/v1/conversations/*` 已实现 —— 创建 POST（201，请求使用 `knowledge_base_id`，对齐 Chat v1 与 §3.1）、列表 GET（200）、详情 GET（200）、重命名 PATCH（200）、删除 DELETE（204）。字段契约以 `docs/openapi/evidsight-v1.yaml` 为唯一权威。legacy `/api/conversations/*` 只作为兼容入口保留（更新使用 `PUT`），按 API.md §15 观测并在 Consumer 迁移、窗口归零后由负责人确认删除。React 问答历史不得以 legacy DTO 固化新 Consumer。ADR 检查 1–8：否（让实现回到既有 API.md §7 目标态，不改变权限模型、服务边界或数据生命周期）。

**Chat 迁移态（2026-08-08）**：`POST /api/v1/chat/stream`、generation 生命周期与幂等 `cancel` 已实现，并按 §12 输出 canonical 事件；React Web 只允许消费 v1。旧入口 `POST /api/chat` 仍使用 `kb_id` 请求字段并输出 `meta`、可选 `thinking`、`message`、`sources`、`finish|error`，Knowledge 回归/评估与性能脚本仍可能是其 Consumer；旧入口保持薄兼容并记录按路由标签区分的废弃调用量。退出门禁为旧入口观测窗口归零、仓库内 Consumer 全部迁移且 v1 Consumer 回归通过；满足后经负责人确认删除旧入口、旧事件适配和对应测试。负责人于 2026-08-08 裁决“实现服从规范”；ADR 检查 1–8：否（让实现回到既有 API、DATABASE 与 FRONTEND 目标态，不改变公共契约、权限或数据生命周期）。裁决与实现记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-08「裁决 M4 SSE 与 Admin 评审阻断项」「补齐 Chat v1 canonical SSE」）。

Chat generation 取消状态机：仅 `pending|running` 可迁移到 `canceled`；对已 `canceled` generation 重复取消返回 `202` 且 `idempotent_replayed=true`；对 `completed|failed` 取消返回 `409 CHAT_GENERATION_STATE_CONFLICT`。generation 不存在或不属于当前创建者统一返回安全 `404 CHAT_GENERATION_NOT_FOUND`，不得借此枚举其他用户的 generation。负责人于 2026-08-08 批准该规范补充；ADR 检查 1–8：否（补齐既有取消端点的局部失败与幂等语义，不改变权限模型、公共机制或数据生命周期）。

外部 API 的字段级请求、响应和事件 `data` Schema 由后续建立的 `docs/openapi/evidsight-v1.yaml` 统一维护；本文只定义行为、权限、状态码和兼容语义。在该 OpenAPI 文件建立前，不得把实现中的临时 DTO 视为已发布契约。

## 8. Research Task API

| 方法与路径 | 权限 | 成功 |
|:---|:---|:---:|
| `POST /api/v1/research/tasks` | 用户 | 202 |
| `GET /api/v1/research/tasks` | owner；admin 审计 | 200 |
| `GET /api/v1/research/tasks/{task_id}` | owner/admin 审计 | 200 |
| `POST /api/v1/research/tasks/{task_id}/cancel` | owner/admin 治理 | 202 |
| `POST /api/v1/research/tasks/{task_id}/resume` | owner/admin 治理 | 202 |
| `DELETE /api/v1/research/tasks/{task_id}` | owner/admin 治理 | 204 |
| `GET /api/v1/research/tasks/{task_id}/events` | owner/admin 审计 | 200 SSE |
| `GET /api/v1/research/tasks/{task_id}/state` | owner/admin 审计 | 200 |
| `GET /api/v1/research/tasks/{task_id}/report` | owner/admin 审计 | 200 |

`state` 与 `report` 为切片 8 收敛时并入 v1 的旧前缀语义等价路由（§8.2）；admin 审计/治理权限当前实现为 owner-only，admin 扩展待 Admin API 切片。

ADR 检查 1–8：否。本节的裁决与验证记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-05「落地 M3 切片 A」「更新 API.md §8」与 2026-08-06「落地 M3 切片 B」条目）；下方为当前契约事实。

### 8.1 创建语义

`POST /api/v1/research/tasks` 必须携带 `Idempotency-Key`（1–128 字符）。同用户同端点同 Key：

- 请求载荷指纹一致：返回首次创建的任务（202，同一 `task_id`，`idempotent_replayed=true`），不重复创建；
- 请求载荷指纹不一致：返回 `409`（迁移期错误码 `E2009 IdempotencyKeyConflict`），不创建新任务。

`request_fingerprint` 由服务端对规范化请求载荷计算（SHA-256，64 位 hex）。`idempotent_replayed` 首次创建为 `false`，重放命中为 `true`；重放时响应返回该任务当前状态，不反映创建时刻。

`knowledge`/`hybrid` 至少选择一个 KB（1–50 个，合法 UUID）；`web` 不接受 KB。创建时仅做上述结构校验；「当前可读」由 Knowledge 在 `/internal/v1/retrieval/search` 对全部目标 KB 实时鉴权，任一不可访问时该次检索整体失败（DATABASE.md §5.2、ADR-010），创建成功不构成对 KB 后续权限的承诺。

Worker 执行时再次核验来源策略依赖（fail-closed，RESEARCH_PIPELINE §1 原则 7/§6.1/§12.1/§12.2）：`knowledge`/`hybrid` 任务必须持有至少一个知识库选择行（DATABASE.md §5.1 不变量）；不变量被破坏时（历史数据、选择行被删等）任务直接进入终态 `failed`（迁移期错误码 `E3114 KnowledgeBasesMissing`，`recoverable=false`），不得静默按 `web` 路径执行或部分放行。

Search 阶段按来源策略分流（RESEARCH_PIPELINE §3/§6.1）：`knowledge` 只走 Internal Retrieval（不调用 Tavily，不创建 Web Source）；`web` 走既有 Tavily 路径；`hybrid` 先执行内部检索再执行 Web 搜索，Web Query 只来自原始 Topic / 公开子问题，内部 excerpt、内部文档标题与内部命名绝不自动进入 Web Query（ADR-010 域隔离）。Internal Retrieval 对全部目标 KB 实时鉴权，任一 KB 无权返回 `KB_FORBIDDEN` 时整次检索失败（迁移期错误码 `E3115 InternalKnowledgeForbidden`，`recoverable=false`，不得降级为 Web）；瞬时不可用重试耗尽返回 `E3116 InternalRetrievalUnavailable`（`recoverable=true`）；响应不符合 Contract 返回 `E3117 InternalRetrievalContract`（`recoverable=false`）。内部命中的 `minimal_excerpt` 只存在于当前 Step 内存，转换后的内部 Evidence 不含任何正文，展开原文必须通过 Knowledge 来源访问 API 实时鉴权。

取消和恢复命令幂等。并发或队列达到上限返回 `429 RS_TASK_CONCURRENCY_LIMIT` 或 `RS_QUEUE_LIMIT`，`retryable=true`。

Task/Phase/Step 枚举由 Research Pipeline 权威定义；API 只暴露状态、进度、时间、可恢复性和安全错误。客户端必须容忍未知非终态枚举。

### 8.2 信封迁移态

当前态：`POST /api/v1/research/tasks` 返回 `{"code":"0","message":"...","data":{...}}`，请求体沿用 `topic + requirements + source_strategy + knowledge_base_ids`，错误信封为 `{"code","message","detail"}`。目标态：API.md §4 `{"error":{...}}` 错误结构与 §3.1 扁平 `ResearchTaskCreate`（含预算摘要）。迁移步骤、Consumer 清单、观测与退出门禁记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-05「更新 API.md §8」条目）。

**端点覆盖迁移态（2026-08-08 切片 8 收敛）**：`/api/v1/research` 已补齐 §8 全部研究命令与查询 —— `POST /tasks`（§8.1 幂等创建）、`GET /tasks`、`GET /tasks/{task_id}`、`POST /tasks/{task_id}/cancel`、`POST /tasks/{task_id}/resume`、`DELETE /tasks/{task_id}`（204）、`GET /tasks/{task_id}/events`（SSE），并收敛旧前缀 `state`/`report` 为 `GET /tasks/{task_id}/state` 与 `GET /tasks/{task_id}/report`（对齐 ROADMAP 2026-08-05「Research API 路径迁移到 /api/v1/research」裁决）。旧前缀 `/api/research` 收敛期间保持可用：改为薄适配器复用同一 application service（`app/api/research_common.py`），每个旧前缀路由入口记录废弃调用量指标 `researchmind_old_api_calls_total`（按路由标签）。**Consumer 清单与退出门禁**：仓库内前端（`apps/web`）当前不调用 Research CRUD 路由；脚本仅 `scripts/smoke_compose.sh` 使用 `/api/research/health`（健康探针，独立于 CRUD 路由）；旧前缀 CRUD 路由删除需满足 §15「废弃路由必须记录调用量；在观测窗口归零且 Consumer 回归通过后才能删除」，观测指标为旧前缀调用量，删除前由负责人确认窗口关闭。此处登记为迁移期事实，不新增契约语义。

**Research SSE 迁移态（2026-08-08）**：v1 `GET /api/v1/research/tasks/{task_id}/events` 已通过独立投影输出 §13 canonical 事件；旧 `/api/research/{task_id}/stream` 继续输出 granular 事件 `task.status.snapshot`、`task.*`、`phase.*`、`step.*`、`checkpoint.saved` 与安全白名单内的 `agent.action|observation`，并保留废弃调用量指标。React Web 只允许消费 v1。退出门禁为旧路由调用量观测窗口归零、仓库内 Consumer 迁移且 canonical Provider/Consumer 回归通过；满足后经负责人确认删除旧 granular 适配。负责人于 2026-08-08 裁决“实现服从规范”；ADR 检查 1–8：否（只修正 v1 Provider 使其符合既有 §13，不改变目标公共契约、任务状态事实或权限）。裁决与实现记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-08「裁决 M4 SSE 与 Admin 评审阻断项」「统一 Research v1 SSE」）。

### 8.3 迁移期错误码映射

Knowledge Internal 返回的新命名空间错误码在 Research 消费端映射为迁移期外部 E 码；信封统一到 §4 目标态前，本表是当前对外语义（对齐文档治理 §5.3）。退出条件：全平台信封统一落地 §4（§8.2）时随迁新码并删除本表与旧 E 码；观测：后端访问日志 `error_code` 分布与错误映射测试。

| 内部返回（Contract / Knowledge） | 迁移期外部 E 码 | 语义 | retryable |
|:---|:---|:---|:---:|
| `AUTH_USER_DISABLED` | `E1010` | 用户禁用或不存在 | 否 |
| `INTERNAL_IDENTITY_UNAVAILABLE` / 网络 / 超时 | `E9002` | 身份事实源不可用，失败关闭 | 是 |
| `INTERNAL_CONTRACT_*` / `INTERNAL_SERVICE_UNAUTHENTICATED` / `EVIDENCE_SOURCE_UNAVAILABLE` | `E3117` | Internal Retrieval Contract 或响应校验失败 | 否 |
| `INTERNAL_RETRIEVAL_UNAVAILABLE` / 限流 / 网络 / 超时 | `E3116` | 内部检索瞬时不可用 | 是 |
| `KB_FORBIDDEN` | `E3115` | 任一目标 KB 无权，整次检索失败 | 否 |
| DATABASE.md §5.1 不变量破坏（无知识库选择行） | `E3114` | Worker 来源策略 fail-closed | 否 |
| Idempotency-Key 同 Key 不同指纹 | `E2009` | 幂等冲突 | 否 |

Knowledge 对外 Auth 仍使用的既有 E 码（如 `E5009` Refresh Token 重放）与信封一并随 §4 目标态迁移；全平台收口后删除。

ADR 检查（2026-08-06）：命中第 3、4 项。负责人豁免 ADR——执行 API.md §4 已批准目标态，不形成新方案选择；记录见 [CHANGELOG](../CHANGELOG.md)。

## 9. Evidence 与 Report API

| 方法与路径 | 权限 | 成功 |
|:---|:---|:---:|
| `GET /api/v1/research/tasks/{task_id}/evidence` | task READ | 200 |
| `GET /api/v1/evidence/{evidence_id}` | task READ | 200 |
| `GET /api/v1/evidence/{evidence_id}/relations` | task READ | 200 |
| `GET /api/v1/reports/{report_id}` | task READ | 200 |
| `GET /api/v1/reports/{report_id}/sections/{section_id}` | task READ | 200 |
| `POST /api/v1/reports/{report_id}/exports` | task READ，P1 | 202 |

Evidence 明确 `internal|web` 来源类型。内部原文链接指向 Knowledge 来源访问端点并实时鉴权；报告不得内嵌可绕过权限的历史正文。外部 Evidence 展示原始 URL 与获取时间。`supports|contradicts|context` 关系和字段 Schema 归 Contract/Research Pipeline。

## 10. Admin API

| 方法与路径 | 成功 | 约束 |
|:---|:---:|:---|
| `GET /api/v1/admin/users` | 200 | admin |
| `POST /api/v1/admin/users/{user_id}/disable` | 200 | 二次确认、原因、审计、幂等 |
| `POST /api/v1/admin/users/{user_id}/enable` | 200 | 不恢复旧 Token/任务 |
| `POST /api/v1/admin/users/{user_id}/password-reset` | 202 | 受控流程，不回传密码 |
| `GET /api/v1/admin/audit/knowledge-bases` | 200 | 审计范围 |
| `GET /api/v1/admin/audit/documents` | 200 | 审计范围；不自动返回私有正文 |
| `GET /api/v1/admin/audit/research-tasks` | 200 | 审计范围 |
| `GET /api/v1/admin/audit/events` | 200 | 治理和安全事件安全摘要 |
| `GET /api/v1/admin/traces/knowledge` | 200 | Knowledge 性能诊断，无正文/Prompt |
| `GET /api/v1/admin/traces/research` | 200 | Research 性能诊断，无正文/Prompt |
| `DELETE /api/v1/admin/governance/{resource_type}/{resource_id}` | 204 | 原因、审计、幂等 |

管理员只能修改 PRD 允许的治理元数据，不能替普通用户上传业务文档。危险操作必须记录操作者、原因、目标、请求 ID 与结果。

完整成本与计费、可配置角色权限和组织级设置属于 P1，不属于 v1.0 P0 Admin API；前端可以保留原型入口，但不得调用未定义接口或展示伪造数据。

## 11. Internal API

ADR 检查 1–8：否。本节新增端点是在未发布的 `1.0.0-draft` Contract 中落实 accepted ADR-005 已确定的 Knowledge 身份事实源和 Service JWT 边界，不改变服务职责、信任方向或既有已发布契约。

### 11.1 内部身份状态 API

`GET /internal/v1/identity/users/{platform_user_id}/status` 是 Research 在创建长期任务前复核 Platform User 当前状态的唯一入口。该端点只允许内部网络中的 Research Service 调用，不得由 Nginx 对外代理，也不得被浏览器或其他终端用户直接调用。

请求必须同时携带 `Authorization: Bearer <service-token>`、`X-EvidSight-Contract-Version`、`X-Request-ID` 和 W3C `traceparent`。路径参数必须是合法 Platform User UUID。Knowledge 固定按“Research 服务身份 → Contract 版本和请求元数据 → 用户状态”顺序校验；任一步失败都不得返回用户资料。Service Token 的 Claim、签发和验证规则引用身份规范与配置规范。

Service Token 缺失或无效返回 `401 INTERNAL_SERVICE_UNAUTHENTICATED`；Contract 版本缺失或不受支持返回 `400 INTERNAL_CONTRACT_UNSUPPORTED`；请求关联字段、Trace Context 或 Platform User UUID 缺失/非法返回 `400 INTERNAL_CONTRACT_INVALID`。认证或请求校验失败不得查询用户状态。

成功返回 `200` 和 Contract `IdentityStatusResponse`，只包含 `contract_version`、`platform_user_id`、`status` 与 `status_version`。不得返回用户名、角色、Knowledge 内部 `users.id` 或其他资料。用户不存在与用户已禁用统一返回 `403 AUTH_USER_DISABLED`，不得让外部调用方区分；身份数据库暂时不可用返回 `503 INTERNAL_IDENTITY_UNAVAILABLE`，`retryable=true`，Research 不得使用旧的 `active` 结果放行新任务。

Research v1.0 在创建任务前实时调用该端点，不缓存用户状态。未来引入状态缓存前，必须先定义短 TTL、`status_version` 比较和禁用事件主动失效机制；不得仅依赖 Access Token 剩余有效期。

### 11.2 检索与原文重取

`POST /internal/v1/retrieval/search` 是 Research 使用 Knowledge 发现候选的唯一搜索入口。请求/响应完整字段、Evidence Contract、固定样例和版本由 `packages/contracts/` 拥有。

`POST /internal/v1/retrieval/resolve` 是 Research 对已选定内部 Candidate 进行精确正文重取的唯一入口。它按 KB、Document、Document Version、Segment 稳定身份读取，不执行相似检索，也不静默切换到新的 Active Version。

HTTP 层必须携带 Research 服务身份、Platform User ID、目标 KB、`X-Request-ID`、调用链 ID 和 Contract 版本。Knowledge 依次验证服务身份、版本/结构、用户启用状态及每个 KB 当前 READ 权限，再执行检索。

主要错误：`INTERNAL_SERVICE_UNAUTHENTICATED`、`INTERNAL_CONTRACT_UNSUPPORTED`、`AUTH_USER_DISABLED`、`KB_FORBIDDEN`、`EVIDENCE_SOURCE_UNAVAILABLE`、`INTERNAL_RATE_LIMITED`、`INTERNAL_RETRIEVAL_UNAVAILABLE`。服务认证成功不能替代用户授权。响应不得暴露 ORM、Chroma Collection、磁盘路径或缓存 Key。

## 12. Chat SSE

响应为 `text/event-stream; charset=utf-8`。每个业务事件包含 `event`、单调 `id` 和 JSON `data`；心跳使用 SSE 注释帧。

| 事件 | 语义 |
|:---|:---|
| `meta` | 请求、generation 和 conversation 标识 |
| `message.delta` | 回答文本增量 |
| `sources` | 已确认来源摘要 |
| `error` | 流内安全错误，随后关闭 |
| `done` | 唯一成功终态 |

事件顺序为 `meta` → 零到多个 delta → sources → done；失败路径不发送 done。终态后禁止业务事件。客户端断开或显式取消可终止生成；已持久化消息的具体时点由 Knowledge Pipeline 定义。

## 13. Research SSE

Research SSE 是持久任务订阅，断开不得取消研究任务。重连携带 `Last-Event-ID` 或等价游标；服务先返回持久状态快照，再发送后续事件。事件可能重复，客户端按事件 ID 幂等消费。

| 事件 | 语义 |
|:---|:---|
| `snapshot` | Task/Phase/Step 持久状态快照 |
| `task.updated` | 任务状态或进度变化 |
| `phase.updated` | 阶段变化 |
| `step.updated` | 步骤变化 |
| `evidence.added` | 新 Evidence 可查询 |
| `report.updated` | 报告版本或章节可查询 |
| `error` | 订阅错误或可公开任务错误 |
| `stream.end` | 本次订阅结束，不代表任务成功 |

任务终态由 Research 状态解析器和 MySQL 事实决定，不由连接状态决定。取消与恢复只通过 Research Task 命令接口完成。

## 14. 健康、就绪与指标

两个服务分别提供 liveness 与 readiness。Liveness 只表明进程可响应；readiness 验证接收业务流量所需依赖。Dependency detail 仅管理员或内部运维可见，不泄露连接串和凭证。`/metrics` 只在内部网络暴露；外部 Nginx 不代理。

外部 Provider 不作为 API 启动硬依赖，但其不可用必须反映在能力状态、任务错误和诊断指标中。

## 15. 兼容、废弃与契约测试

- 兼容层不得改变权限、状态机、SSE 或错误安全边界。
- 废弃路由必须记录调用量；在观测窗口归零且 Consumer 回归通过后才能删除。
- Contract Breaking Change 使用新版本，不静默改变字段含义。
- Internal Retrieval 必须有 Provider/Consumer 固定样例测试，验证版本、成功、权限拒绝和未知字段。
- Chat 与 Research SSE 分别拥有顺序、终态、断线和重连测试，不用同一业务 Fixture 互相替代。

## 16. 验收映射

| PRD 需求 | API/协议入口 |
|:---|:---|
| FR-ID-001 | Auth API、统一 Bearer 验证 |
| FR-KB-001、FR-KB-002、FR-KB-003 | Knowledge Base、Document、来源位置 API |
| FR-QA-001、FR-QA-002 | Chat SSE、Conversation API |
| FR-RS-001、FR-RS-002、FR-RS-003、FR-RS-004 | Research Task API、Research SSE |
| FR-EV-001、FR-EV-002、FR-EV-003、FR-EV-004 | Evidence API、Internal Retrieval、实时来源鉴权 |
| FR-RP-001、FR-RP-002、FR-RP-003 | Report API、Evidence/引用联动数据 |
| FR-AD-001、FR-AD-002 | Admin API 与治理审计 |

PRD §13 的十个端到端场景分别由文档入库/Chat、KB 越权、web/knowledge/hybrid Research、冲突 Evidence、取消、恢复、历史报告二次鉴权和管理员禁用链路覆盖。测试矩阵与门禁由 `docs/specs/TESTING.md` 定义，命令和记录格式见 `docs/guides/TEST_EXECUTION.md`；实际结果进入对应评审或发布记录，不在本文伪造完成状态。
