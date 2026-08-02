# 据见（EvidSight）API 与事件协议

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认设计 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-08-02 |

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
- ID 对外为不透明 UUID 字符串，客户端不得依赖排序或内部主键。
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

在 OpenAPI 落地前，下列字段是实现与测试不得偏离的最小基线；OpenAPI 建立后成为字段、类型和约束的唯一权威源，本文改为引用。

| DTO | 必需字段 | 关键约束 |
|:---|:---|:---|
| `LoginRequest` | `username`、`password` | 非空；错误不区分账号不存在和密码错误 |
| `UserSummary` | `id`、`username`、`role`、`status` | UUID；`role=user|admin`，`status=active|disabled` |
| `KnowledgeBaseCreate` | `name`、`visibility` | `visibility=private|public` |
| `KnowledgeBaseResponse` | `id`、`name`、`visibility`、`owner`、`index_status`、时间 | 不返回内部主键、Collection 或路径 |
| `DocumentResponse` | `id`、`knowledge_base_id`、`display_name`、`status`、时间 | `queued|processing|completed|partial|failed` |
| `ChatStreamRequest` | `conversation_id`、`knowledge_base_id`、`message` | v1.0 只有单数 KB；消息非空 |
| `ConversationResponse` | `id`、`knowledge_base_id`、`title`、时间 | 会话只属于一个用户和一个 KB |
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
| `POST /api/v1/auth/login` | 匿名、限流 | 200 | 登录并建立 Refresh Family |
| `POST /api/v1/auth/refresh` | Refresh Token | 200 | 原子轮换；重放撤销 Family |
| `POST /api/v1/auth/logout` | 可识别会话 | 204 | 幂等撤销并清理 Cookie |
| `GET /api/v1/auth/me` | 用户 | 200 | 返回最小用户与角色摘要 |

认证、轮换、禁用、Cookie/CSRF 和安全错误以身份规范为准。

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

### 6.2 Document 与来源

| 方法与路径 | 权限 | 成功 | 说明 |
|:---|:---|:---:|:---|
| `POST /api/v1/knowledge-bases/{kb_id}/documents` | owner | 202 | 提交事务后分发入库 |
| `GET /api/v1/knowledge-bases/{kb_id}/documents` | KB READ | 200 | 是否展示分块受权限约束 |
| `GET /api/v1/documents/{document_id}` | KB READ | 200 | 返回状态与安全元数据 |
| `POST /api/v1/documents/{document_id}/retry` | owner | 202 | 仅允许可重试状态，幂等 |
| `DELETE /api/v1/documents/{document_id}` | owner/admin 治理 | 204 | 异步清理另有状态字段 |
| `GET /api/v1/documents/{document_id}/locations/{location_id}` | 当前 READ | 200 | 实时鉴权后返回最小片段和定位 |

文档状态至少表达 queued、processing、completed、partial、failed。只有满足 Pipeline 有效来源条件的文档可参与检索。

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

创建必须使用 `Idempotency-Key`。`knowledge`/`hybrid` 至少选择一个当前可读 KB；`web` 不接受内部 KB。取消和恢复命令幂等。并发或队列达到上限返回 `429 RS_TASK_CONCURRENCY_LIMIT` 或 `RS_QUEUE_LIMIT`，`retryable=true`。

Task/Phase/Step 枚举由 Research Pipeline 权威定义；API 只暴露状态、进度、时间、可恢复性和安全错误。客户端必须容忍未知非终态枚举。

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

## 11. Internal Retrieval API

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

PRD §13 的十个端到端场景分别由文档入库/Chat、KB 越权、web/knowledge/hybrid Research、冲突 Evidence、取消、恢复、历史报告二次鉴权和管理员禁用链路覆盖。实际测试名称、环境和结果记录在 `docs/specs/TESTING.md`，不在本文伪造完成状态。
