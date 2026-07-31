# EvidSight 剩余设计文档第一批设计

| 属性 | 值 |
|:---|:---|
| 状态 | 已确认，待落盘实施 |
| 日期 | 2026-07-31 |
| 范围 | 文档清单对齐、统一身份与权限、API 协议基线 |

## 1. 背景与问题

EvidSight 已有 PRD、总体架构、路线图和 Monorepo 迁移计划，但业务实现所需的专项规范尚未完成。当前三份权威文档对后续文档的列举不完全一致：

- `docs/PRD.md` §14 未列出 Knowledge/Research 数据库设计、统一身份与权限、数据迁移与测试策略；
- `docs/ARCHITECTURE.md` §17 要求统一身份与权限、数据迁移和测试策略等专项设计；
- `docs/ROADMAP.md` §4 给出了依赖顺序，但未为所有架构要求提供明确文件路径。

若直接编写字段级 API，JWT Claim、服务凭证、实时授权和敏感数据外发语义可能被重复定义或出现隐性冲突。因此第一批文档先统一目录，再分别建立身份权限与 API 两个权威边界。

## 2. 目标与非目标

### 2.1 目标

1. 对齐 PRD、ARCHITECTURE 和 ROADMAP 中的专项文档清单、文件路径和编写顺序。
2. 建立 `docs/IDENTITY_AND_ACCESS.md`，作为身份、授权和敏感数据外发策略的唯一权威规范。
3. 建立 `docs/API.md`，作为外部/内部 HTTP、错误语义和 SSE 协议的唯一权威规范。
4. 明确 `packages/contracts/` 与 API 文档的分工，避免字段定义重复漂移。
5. 为后续 Contract、数据库、Pipeline 和前端规范提供稳定输入。

### 2.2 非目标

- 本批次不创建生产代码、数据库迁移或运行时配置。
- 本批次不完成 `packages/contracts/` 的可执行 Schema。
- 本批次不详细定义 Knowledge/Research 数据表和 Pipeline 内部算法。
- 本批次不改变已确认的服务所有权、网络边界、权限矩阵和 v1.0 产品范围。
- 本批次不声称 Monorepo 迁移或 v1.0 发布已经完成。

## 3. 权威文档边界

| 事实类型 | 唯一权威文档 | 其他文档的处理方式 |
|:---|:---|:---|
| 产品目标、用户、功能、产品级权限矩阵和验收指标 | `docs/PRD.md` | 交叉引用，不复制 |
| 服务所有权、网络、部署和系统级非功能要求 | `docs/ARCHITECTURE.md` | 交叉引用，不复制 |
| JWT Claim、令牌生命周期、禁用语义、服务凭证、授权上下文、敏感数据外发策略 | `docs/IDENTITY_AND_ACCESS.md` | API 只描述如何携带和失败 |
| 路由、HTTP 方法、状态码、错误码、分页、幂等、并发限制和 SSE | `docs/API.md` | Contract 引用协议语义 |
| 跨服务请求/响应/Event/Evidence 字段 Schema、版本和固定样例 | `packages/contracts/` | API 链接契约版本，不复制完整 Schema |
| 服务内部数据表、索引、外键和迁移 | 各服务 `docs/DATABASE.md` | API/Pipeline 只引用业务对象 |
| 检索与研究状态机、阶段、算法和降级 | 各服务 Pipeline 文档 | API 只暴露外部可观察状态 |

## 4. 第一批交付内容

### 4.1 文档清单对齐

同步修改：

- `docs/PRD.md` §14；
- `docs/ARCHITECTURE.md` §17；
- `docs/ROADMAP.md` §4 与 §7。

三处统一列出：身份权限、API、Contract、Knowledge/Research Database、Knowledge/Research Pipeline、Frontend、UI Design、数据迁移、测试策略、CHANGELOG 和 ADR。ROADMAP 保留依赖顺序；PRD 与 ARCHITECTURE 只说明关系和边界。

### 4.2 统一身份与权限设计

`docs/IDENTITY_AND_ACCESS.md` 至少定义：

- Platform User ID 与 `user`/`admin` 角色语义；
- Access Token 和 Refresh Token 的签发、验证、刷新、轮换、撤销及退出；
- 两个服务共同验证的必需 JWT Claims、算法与时间语义；
- 禁用用户在登录、刷新、现有 Access Token、研究创建和内部检索上的行为；
- Research → Knowledge 的服务认证与终端用户授权上下文；
- 管理员治理、资源所有权和知识库可见性的组合规则；
- 报告内部证据原文的实时二次鉴权；
- 私有知识进入外部模型或搜索服务前的默认拒绝、显式允许、脱敏和审计规则；
- 密钥轮换、兼容、失败、审计与验收场景。

服务凭证只能认证调用服务，不能替代用户授权。Knowledge Service 必须依据当前用户与知识库状态重新计算 READ 权限。

### 4.3 API 协议设计

`docs/API.md` 至少定义：

- 外部 API 的 `/api/v1/*` 正式命名空间；
- Internal Retrieval 的 `/internal/v1/retrieval/*` 命名空间；
- 迁移期旧路由兼容适配和废弃规则；
- 统一请求头、时间、ID、分页、排序、过滤和幂等语义；
- 统一成功响应约定与错误响应结构；
- Auth、Knowledge Base、Document、Chat、Conversation、Research Task、Evidence、Report 和 Admin 的端点目录；
- Internal Retrieval 的调用前置条件、实时权限验证、错误与限流语义；
- Chat SSE 与 Research SSE 的独立事件目录、终态、断线和重连行为；
- 健康检查、就绪检查、依赖详情与 Metrics 的可见范围；
- 版本兼容、Breaking Change 和契约测试要求。

统一错误响应至少包含稳定 `error_code`、可公开消息、`request_id` 和 `retryable`。错误不得包含文档正文、凭证、SQL、内部路径或堆栈。

## 5. SSE 边界

### 5.1 Chat SSE

- 属于单次 HTTP 请求生命周期；
- 传输回答片段、来源和请求终态；
- 客户端断开可触发当前生成中止；
- 具体消息持久化时点由 Knowledge Pipeline/Chat 专项规范定义；
- 不与 Research Task 状态事件复用业务事件名称或状态机。

### 5.2 Research SSE

- 属于持久研究任务的状态订阅；
- 断开不得取消研究任务；
- 重连先返回 MySQL 持久状态快照，再发送后续事件；
- Task/Phase/Step 终态由统一状态解析器决定；
- 取消与恢复通过独立命令接口完成，不由 SSE 连接状态驱动。

两者可以复用 SSE 帧解析基础规范，但不能合并业务事件协议。

## 6. 版本与迁移策略

- 新的正式外部协议使用 `/api/v1/*`。
- Internal API 从第一版即使用 `/internal/v1/*`，且不得通过 Nginx 对外暴露。
- 原 DocMind/ResearchMind 路由在 Monorepo 迁移期保持行为不变，通过兼容层逐步映射；废弃前必须记录调用方、提供替代路径并通过回归测试。
- Breaking Change 使用新版本或显式兼容迁移，不静默改变字段语义。
- 第一批规范不得把尚未实现的接口标记为“已上线”。

## 7. 失败、安全与审计

- 认证失败返回 `401`，已认证但无权操作返回 `403`，资源不存在或按防枚举策略隐藏时使用文档明确的 `404` 语义。
- 并发或队列达到限制时返回可重试业务错误，不同步执行长任务、不静默丢弃。
- Research Service 传入的用户 ID、知识库 ID 和授权结论均不被 Knowledge Service 直接信任。
- 请求日志和审计记录携带 `request_id`；跨服务调用继续传播调用链上下文。
- 外部错误仅暴露安全摘要，详细诊断保留在受控日志和 Trace 中。

## 8. 验收标准

第一批文档完成时必须满足：

1. PRD、ARCHITECTURE、ROADMAP 对所有专项文档的路径、顺序和权威边界不存在冲突。
2. 身份文档能够为登录、刷新、退出、禁用、服务调用和实时授权导出明确测试场景。
3. API 文档中的每个 P0 功能需求至少映射到一个端点或 SSE 行为。
4. API 文档不复制跨服务 Contract 的完整字段 Schema，也不定义数据库或 Pipeline 内部实现。
5. Chat SSE 与 Research SSE 的断线、取消、重连和终态语义无歧义。
6. Internal Retrieval 明确同时验证服务身份、用户身份、请求上下文和知识库实时 READ 权限。
7. 文档不包含 `TBD`、`TODO`、失效链接或未解释占位符。
8. 执行 Markdown 链接、标题层级、术语和跨文档一致性检查并记录结果。

## 9. 后续依赖顺序

第一批规范确认后，剩余设计按以下顺序推进：

1. `packages/contracts/`；
2. `services/knowledge/docs/DATABASE.md` 与 `RAG_PIPELINE.md`；
3. `services/research/docs/DATABASE.md` 与 `RESEARCH_PIPELINE.md`；
4. `apps/web/docs/FRONTEND.md`；
5. `apps/web/docs/UIDESIGN.md`；
6. 数据迁移与回滚方案；
7. 测试策略与发布验收清单；
8. 持续维护 `docs/CHANGELOG.md` 与 `docs/decisions/`。

每一批都遵循“权威规范确认 → 可验证验收条件 → 实施计划 → 实现/迁移”的门禁。
