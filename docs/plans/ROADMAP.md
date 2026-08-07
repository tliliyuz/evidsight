# 据见（EvidSight）产品实施路线图

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-08-06 |
| 排期方式 | 阶段里程碑与验收门禁，不绑定具体日期 |

> 本文档是据见实施顺序、阶段依赖和发布门禁的权威计划。产品范围与成功指标见 [PRD.md](../specs/PRD.md)，总体服务边界与部署约束见 [ARCHITECTURE.md](../specs/ARCHITECTURE.md)，第一阶段代码布局迁移步骤见 [MONOREPO_MIGRATION_PLAN.md](MONOREPO_MIGRATION_PLAN.md)。字段、状态机、算法和界面细节由对应专项规范定义，本文不复制其定义。

## 1. 定位与使用原则

### 1.1 文档目标

本路线图回答以下问题：

- 据见 v1.0 应按什么顺序交付；
- 每个阶段依赖哪些已确认规范和前置结果；
- 每个阶段产出什么可审查、可验证的交付物；
- 满足哪些条件后才能进入下一阶段；
- 哪些能力属于 v1.x，哪些能力明确延后。

路线图不承担任务级排期、字段级设计或代码实施步骤。具体工作分解应在对应专项设计确认后单独编写实施计划。

### 1.2 实施原则

1. **规范先行**：业务行为先在权威规范中定义，再由验收条件和测试驱动实现。
2. **契约先行**：跨服务请求、响应、错误和 Evidence 先形成版本化 Contract，再实现 Provider 与 Consumer。
3. **纵向可验收**：每个里程碑必须形成可独立验证的业务或工程结果，不以“代码已写完”代替验收。
4. **边界不倒退**：Research Service 不得直读 Knowledge Service 的业务库、向量目录、上传文件或 ORM Model。
5. **证据优先**：Evidence Graph 是可复用资产，报告是其版本化表达；结论必须可追溯到证据。
6. **安全默认开启**：权限、隐私、审计和恢复不是发布前补丁，必须随各阶段同步交付。
7. **试点资源约束**：v1.0 以单机 Docker Compose、2 vCPU / 2 GB RAM 为部署基线，优先保证核心链路稳定和可恢复。

### 1.3 状态定义

| 状态 | 定义 |
|:---|:---|
| 未开始 | 进入条件尚未满足，或尚未投入实施 |
| 进行中 | 进入条件已满足，正在完成规范、实现或验收 |
| 受阻 | 存在明确阻塞条件，且已记录解除条件 |
| 已完成 | 本阶段全部退出门禁已有可复核证据 |

禁止以主观完成比例替代门禁结果。阶段状态变化必须有对应的测试、评审、演练或发布记录。

## 2. 里程碑总览

| 里程碑 | 状态 | 阶段名称 | 核心结果 | 主要依赖 |
|:---|:---|:---|:---|:---|
| M0 | 已完成 | 规范基线与 Monorepo 迁移 | 两个来源项目进入统一仓库并保持独立构建、测试和数据边界 | 已确认 PRD、总体架构、来源基线 |
| M1 | 已完成 | 统一身份、权限和基础契约 | 建立跨服务可信身份、权限语义、服务认证与 Contract 基线 | M0 |
| M2 | 已完成 | Knowledge Service 稳定化与 Internal Retrieval | 企业知识通过权限感知的内部检索契约向研究链路提供 Evidence | M1 的身份与 Contract 基线 |
| M3 | 进行中 | Research Service 接入内部知识 | 打通 `knowledge`、`web`、`hybrid` 三类研究来源和可恢复研究链路 | M2 |
| M4 | 未开始 | 统一 Web、报告与证据联动 | 用户通过统一界面完成问答、研究、报告阅读和证据复核 | M2、M3 的稳定 API 与事件 |
| M5 | 未开始 | 治理、可观察性和部署验收 | 形成可管理、可诊断、可备份、可恢复的 2C2G 试点部署 | M1—M4 |
| M6 | 未开始 | v1.0 发布门禁与后续演进 | 全部 P0、成功指标和端到端场景完成发布验收 | M0—M5 |

M0 的结构迁移与单机运行基线已完成。原 `docs/migration/` 下的迁移过程记录已由负责人于 2026-08-02 主动删除，不再作为阶段状态门禁；当前仓库结构、保留的 Git 历史和 `docs/specs/TESTING.md` 中的可重复验证命令是后续复核入口。统一身份、Internal Retrieval、Research 前端整合及生产数据迁移仍属于后续里程碑，不因 M0 完成而视为完成。

总体主线为：`M0 → M1 → M2 → M3 → M4 → M5 → M6`。

## M0：规范基线与 Monorepo 迁移

### 阶段目标

冻结可复核的产品与架构基线，将 DocMind 与 ResearchMind 按已确认边界迁入 EvidSight Monorepo，建立统一仓库控制层和单机编排骨架，同时保持两个服务的业务行为、依赖、测试和数据所有权独立。

### 进入条件

- `docs/specs/PRD.md` 已确认产品定位、P0/P1/P2 和验收场景；
- `docs/specs/ARCHITECTURE.md` 已确认服务边界、部署基线和数据隔离；
- DocMind 与 ResearchMind 来源提交已冻结，未提交改动已人工确认；
- Monorepo 迁移范围不包含业务行为、Schema、API 或 SSE 语义变更。

### 范围内工作

- 验证两个来源仓库的固定提交和测试基线；
- 建立根目录测试、构建、编排和仓库约束；
- 保留 Git 历史导入 Knowledge Service、Research Service 和统一 Web 基线；
- 建立 `packages/contracts/`、`deploy/` 和共享前端包的边界占位；
- 建立独立服务构建上下文、命名空间队列和 2C2G Compose 骨架；
- 验证迁移前后同一测试集结果一致。

### 必须完成的规范

- `docs/plans/MONOREPO_MIGRATION_PLAN.md`；
- 根目录 `CLAUDE.md` 与 `AGENTS.md` 的 SDD、TDD 和服务边界约束；
- 来源基线结果、迁移验收记录和回滚说明。

### 主要交付物

- `apps/web/` 统一前端基线；
- `services/knowledge/` 独立 Knowledge Service；
- `services/research/` 独立 Research Service；
- `packages/contracts/` 跨服务契约边界；
- 根目录 Compose、Nginx、测试和 smoke 验证入口；
- 可审查的迁移历史与基线验证证据。

### 退出门禁

- 迁移计划中的八项任务全部完成并有实际验证结果；
- 两个后端和前端在迁移前后保持测试与构建等价；
- 两个 Python 服务仍可独立安装依赖、迁移数据库和运行测试；
- Research Service 无任何对 Knowledge 数据库、ChromaDB 或上传卷的直接依赖；
- Compose 骨架可以完成配置解析、容器构建和基础 smoke 验证；
- 当前结果被明确标记为“代码布局基线”，未被误称为 v1.0 可发布版本。

### 本阶段不做

- 不统一两个后端的业务模型、数据库或 Alembic 历史；
- 不实现统一身份、Internal Retrieval 或统一研究前端；
- 不修改现有 API、权限、状态机或 SSE 行为；
- 不导入未经规范化的新业务能力。

## M1：统一身份、权限和基础契约

### 阶段目标

建立两个服务共同信任的用户身份、权限和服务间调用基础，定义跨服务对象的版本化契约，使后续 Internal Retrieval 和 Evidence 融合可以在明确边界内实施。

### 进入条件

- M0 已通过退出门禁；
- Platform User ID、Knowledge 数据所有权和 Research 数据所有权保持总体架构定义；
- 身份、权限或 Contract 的行为变更尚未进入生产实现。

### 当前准备门禁

- [x] M0 状态确认为完成；原 `docs/migration/` 过程记录已由负责人删除且不再构成门禁。
- [x] IA-001—IA-012、权限矩阵和 Contract 门禁已拆分为可执行验收测试场景；各切片 RED/GREEN 与六条退出门禁证据见 [CHANGELOG](../CHANGELOG.md)（2026-08-02—08-04 条目）；`ADR-005` 已接受为 `accepted`。

M1 已完成（2026-08-04）。IA-006—IA-009 与 Retrieval/Evidence Contract 依赖 Internal Retrieval，明确划入 M2/M3。


### 范围内工作

- 定义统一 Access Token、Refresh Token、JWT Claims、过期和吊销语义；
- 定义用户禁用后登录、刷新、现有 Access Token 和任务创建行为；
- 定义 `user/admin`、Knowledge Base 所有权、可见性和研究任务访问矩阵；
- 定义 Research Service 调用 Knowledge Service 的服务凭证、用户上下文和审计上下文；
- 定义 API 版本、跨服务错误语义、兼容与弃用规则；
- 建立 Internal Retrieval 与 Evidence Contract 的基础类型、样例和 Provider/Consumer 测试框架。

### 必须完成的规范

- `docs/specs/API.md` 中的统一认证、服务认证、错误码和版本规则；
- `packages/contracts/` 中的基础请求、响应、错误与 Evidence 类型；
- Knowledge 与 Research 数据库规范中与统一用户 ID 相关的引用规则；
- 身份、权限和敏感数据外发策略 ADR。

### 主要交付物

- 统一登录、刷新、退出与禁用用户行为；
- 两个服务一致的 JWT 校验实现；
- 服务间认证和请求审计上下文；
- 权限矩阵自动化测试；
- Contract Schema、固定样例与兼容性测试入口。

### 退出门禁

- 两个服务对相同 JWT Claims、过期和禁用语义的测试结果一致；
- 被禁用用户不能刷新凭证、创建新任务、Chat、上传、重处理或治理写操作；
- 服务间请求无法仅凭用户输入伪造服务身份或授权结论；
- 知识库 READ、WRITE 和管理权限均由明确矩阵覆盖；
- 跨服务 Contract 具备版本、样例、Provider 测试和 Consumer 测试；
- 密钥、Token、密码和内部异常不会进入前端响应或普通日志。

### 本阶段不做

- 不建立独立 Identity Service；
- 不实现企业 SSO、SAML、SCIM 或完整组织模型；
- 不实现指定用户共享、部门空间或完整 ACL；
- 不在 Contract 中暴露 ORM Model、磁盘路径、缓存 Key 或向量存储实现。

## M2：Knowledge Service 稳定化与 Internal Retrieval

### 阶段目标

在迁入后的 Knowledge Service 中稳定文档入库、企业知识问答和证据返回能力，通过权限感知的 Internal Retrieval API 为 Research Service 提供内部知识，同时保持 Knowledge 数据与实现细节封装。

### 进入条件

- M1 的身份、服务认证、错误语义和基础 Contract 已确认；
- Knowledge Service 迁移后回归测试通过；
- Internal Retrieval 的请求方、数据所有者和实时授权责任已明确。

### 当前状态

- [x] `ADR-007` 已接受为 `accepted`（命中检查项 4、5，2026-08-04）；检索权限语义由 `ADR-002`/`ADR-005` 交叉引用覆盖，不另建重复 ADR。
- [x] Internal Retrieval/Evidence Contract、权限感知 Provider 端点、版本化写路径与 PRD AC-005/006/010 真机验收均已落地；契约/Provider/全量测试结果与异常演练记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-04、2026-08-05 条目）。


### 范围内工作

- 稳定文档上传、解析、结构化分块、Embedding、索引、重处理和删除链路；
- 稳定意图识别、问题重写、混合检索、融合、粗排、Rerank 和问答 SSE；
- 定义并实现权限感知的 `/internal/v1/retrieval/*`；
- 返回可供研究链路消费的内部 Evidence、相关性信息和来源位置；
- 支持页码、章节和片段的稳定回溯；
- 打通缓存失效、删除一致性、失败清理和入库恢复；
- 建立固定知识评估集和 Recall@5 验证入口。

### 必须完成的规范

- `docs/specs/API.md` 中的 Knowledge 外部 API 与 Internal Retrieval API；
- `packages/contracts/` 中的 Internal Retrieval 与内部 Evidence Contract；
- `services/knowledge/docs/DATABASE.md`；
- `services/knowledge/docs/RAG_PIPELINE.md`；
- 文档生命周期、检索权限和删除一致性相关 ADR。

### 主要交付物

- 可独立运行和测试的 Knowledge API 与 Worker；
- 权限感知的内部检索 Provider；
- 内部 Evidence 与文档位置返回能力；
- Provider Contract 测试与固定评估集；
- 企业知识问答、会话和来源定位能力。

### 退出门禁

- 文档入库、重处理、删除和失败恢复通过自动化与异常演练；
- private Knowledge Base 的未授权检索路径为零；
- Internal Retrieval 对每次请求实时校验用户与知识库 READ 权限；
- Internal Retrieval Provider 测试与共享 Contract 样例一致；
- 内部 Evidence 可定位到用户当前有权访问的文档位置；
- Research Service 无需了解 Knowledge 数据库、Chroma Collection、缓存或文件路径；
- PRD AC-005、AC-006 和 AC-010 对应验证入口已建立。

### 本阶段不做

- 不把 Research Task、Agent Runtime 或 Evidence Graph 逻辑放入 Knowledge Service；
- 不为 Research Service 提供数据库账号或共享 ORM；
- 不实现跨任务 Evidence Graph 复用；
- 不提前实现 P1 的高级导出或报告版本功能。

## M3：Research Service 接入内部知识

### 阶段目标

使 Research Service 只通过 Internal Retrieval Contract 使用企业知识，完整支持 `knowledge`、`web`、`hybrid` 三类来源策略，并形成可取消、可恢复、可审计的深度研究闭环。

### 进入条件

- M2 的 Internal Retrieval Provider 和权限测试通过；
- Research Pipeline 迁移后现有 Web 研究行为保持回归通过；
- 三类来源策略和 Evidence Contract 已在 PRD/API/Contract 中对齐。

进入条件核验（2026-08-05）：三项核验通过（M2 验收记录、Research 全栈运行基线、三类来源策略与 Evidence Contract 对齐），`ADR-008`/`ADR-009`/`ADR-010` 已接受为 `accepted`（命中项与裁决见各 ADR 及 [CHANGELOG](../CHANGELOG.md) 2026-08-05 条目）；另裁决 Research API 路径按 API.md 迁移到 `/api/v1/research`。

### 当前状态

- [x] 切片 A：#4 数据层、#5 请求契约、#6 幂等创建、#7 Worker 来源策略 fail-closed 守卫（E3114）。
- [x] 切片 B（Knowledge Search Tool）：Internal Retrieval Consumer 客户端、策略感知 `run_search` 分流、Web Query 域隔离（ADR-010）、内部候选持久化删除 `minimal_excerpt`。
- [x] 切片 C（Rerank 内部候选接入 + Evidence 分型，2026-08-06）：`evidence_items` 分型数据层（`source_type=internal|web`、内部稳定 ID/显示/位置/时间/评分摘要/validity 列、`content`/`source_id` 可空、内部唯一键，迁移 `c0d1e2f3a4b5`）；Rerank 策略感知（knowledge 经 resolve 重取内部候选精排、hybrid 与 Web 统一精排、产出 internal 无正文证据、resolve 失败 fail-closed）；Synthesis/Evidence Graph/Render 消费 internal 证据（resolve 重取工作集、区分来源、无正文持久化）。
- [x] 切片 D（租约+取消+恢复数据层与协议，2026-08-06）：`research_tasks` 新增取消请求列（`cancel_requested_at`）、租约列（`lease_owner`/`lease_expires_at`/`lease_generation`）、恢复列（`recovery_count`/`last_completed_step_id`）与索引 `(status, lease_expires_at)`（迁移 `d1e2f3a4b5c`，真实 MySQL upgrade/downgrade 往返验证）；租约协议原语（条件领取/续租/释放 + `is_step_commit_allowed` generation 条件提交）；取消请求化（`cancel_task` 只写 `cancel_requested_at`，Worker 安全检查点停止后由 TaskStateResolver 推导 `canceled`/`partially_completed` 终态，重复取消幂等）；Recovery Scanner 按 `(status, lease_expires_at)` 扫描、遗留 running Step 置 retrying、清除旧 owner、递增 `recovery_count` 并重投递。验证：research 全量 unit（非 slow）854 通过、1 跳过、0 失败（`test_llm` 环境依赖，与本切片无关）、契约 73 项全绿、Architecture 17 项全绿；新增 `test_task_lease` 15 项、`test_cancel_request` 7 项、`test_recovery_lease` 7 项。
- [x] 切片 E（租约接入 AgentRuntime，2026-08-06）：将切片 D 的租约协议接入 `AgentRuntime`——`start_research_task` 在 pending 正常路径与 running 崩溃恢复路径统一领取新 generation 并绑定到 `TaskLockHandle`（条件领取失败即放弃启动并释放锁，防双 Worker）；`TaskLockHandle` 承载 DB 租约续租（刷新循环内，独立会话）与释放（`release()` 清除 owner），绑定 `worker_id`/`lease_generation` 供提交校验；`_complete_step`/`_fail_step` 提交前经 `is_step_commit_allowed` 做 generation 条件门禁（失去租约的 Worker 抛 `LeaseLostError` 立即停止、不提交业务结果）；`_finalize_task` 终态推导前经 `is_task_ownership_valid` 校验所有权（允许取消后 Resolver 推导 canceled）；`_handle_fatal_error` 对 `LeaseLostError` 不写 failed 终态（交由 Recovery Scanner 接管）；取消检查点从旧 `status==canceled` 修正为检测 `cancel_requested_at`（§13.2 取消是请求），取消后安全停止进入 `_finalize_task` 由 Resolver 推导终态并发布 `task.canceled`。验证：RED 确认（`LeaseLostError` 缺失 + `bind_lease`/租约领取缺失导致用例失败）；docker 容器内 research 全量 unit（非 slow）865 通过、1 跳过、1 failed（`test_llm` 环境依赖，与本切片无关）、AgentRuntime 集成 2 项通过、契约 73 项 + `packages/contracts/tests` 131 项全绿、Architecture 17 项全绿；新增 `test_task_lease_wiring` 5 项（pending/running 领取绑定、领取失败释放锁、release/renew 清 owner 续租）、`test_runtime_lease` 6 项（Step 提交放行/拒绝、失败 Step 拒绝、LeaseLostError 不写 failed、取消停止进入最终化）。
- [x] 切片 F（SSE 持久游标 + agent_events 表，2026-08-06）：新增 `agent_events` 追加式业务执行审计表（迁移 `e2f3a4b5c6d`，`(task_id, sequence)` 唯一作 SSE 持久游标，真实 MySQL upgrade/downgrade 往返验证）；AgentEvent Service（event_type 白名单、单调 sequence、游标回放、摘要剥离禁止字段）；AgentEventRecorder 接入 AgentRuntime（`phase.enter`/`tool.request`/`tool.result` 落库并带持久 sequence 发布 SSE，与 Step 同事务提交）；移除 `agent.thought`（模型隐藏推理不外发，§16/§17.3-22）；`sse_event_stream` 支持 `Last-Event-ID` 游标回放（先快照、再回放游标后事件、事件缺口以新快照收敛、不依赖 Redis 历史），API `GET .../stream` 读取 `Last-Event-ID` 注入回放。验证：RED 确认（15 项新增用例 collection 失败）；本地全量 unit（非 slow）882 通过、1 跳过、1 failed（`test_llm` 环境依赖，与本切片无关）、AgentRuntime 集成 2 项通过、契约 73 项 + `packages/contracts/tests` 131 项全绿、Architecture 17 项全绿；新增 `test_agent_event_service` 8 项、`test_agent_event_recorder` 3 项、`test_sse_cursor` 4 项。`agent_memory_entries`（ReAct 工作记忆）仍保留用于内部断点续跑，删除与工作集重建依赖 §13.4 留待后续。
- [x] 切片 G（预算冻结/预留/结算 + 预算停止终态 + 报告披露，2026-08-06）：服务端默认推导冻结上限（零公共契约变更，负责人确认）；`research_tasks` 新增 `budget_frozen`/`budget_usage`/`budget_stopped_at`（迁移 `f3g4h5i6j7k`，MySQL 往返验证）；BudgetService（derive/freeze/can_reserve/settle_budget/停止判定，knowledge 无 Fetch）；AgentRuntime 接入（Tool 前预留、结果后结算、`BudgetExhaustedError` 安全停止、budget.stop agent_event）；Resolver 预算停止终态（§14 不是自动成功：已有 Evidence 过完整度硬门槛 → partial，否则 failed E3103）；renderer 预算停止时向 knowledge_gaps 注入披露。验证：RED 确认（25 项新增用例失败）；docker 容器内 research 全量 unit（非 slow）905 通过、1 跳过、1 failed（`test_llm` 环境依赖，与本切片无关）、AgentRuntime 集成 + 契约 75 项 + `packages/contracts/tests` 131 项 + Architecture 17 项全绿；本地 16 项失败与 clean HEAD 失败集一致（既有环境依赖）；新增 `test_budget_service` 15 项、`test_task_state_resolver_budget` 5 项、`test_runtime_budget` 3 项、`test_report_budget_disclosure` 3 项。429 并发/队列限制（`RS_TASK_CONCURRENCY_LIMIT`/`RS_QUEUE_LIMIT`）留待 API 目标态信封迁移。
- [x] 切片 H（AC 验证入口，2026-08-07）：落地 M3 退出门禁「PRD AC-001、AC-003、AC-004 和 AC-010 对应验证入口已建立」——Research 侧 `scripts/verify_ac001_claim_evidence.py`（报告章节 [来源N] 引用闭合率 ≥ 90%）、`verify_ac003_task_success.py`（冻结评估集任务成功率 ≥ 95%，排除用户主动取消）、`verify_ac004_recovery_drill.py`（Worker 中断 + 租约恢复演练成功率 ≥ 95%）、`verify_ac010_traceability.py`（Evidence 分型/定位/URL/获取时间追溯率 100%）四个脚本，均输出 TESTING.md §7 发布记录模板、缺失数据报错退出不伪造；共享纯函数 `app/evaluation/ac_metrics.py`（引用闭合/成功率/恢复率/可追溯性，23 项单测）；冻结评估集 `tests/eval/research_eval_set.json`（6 题，覆盖 comparison/explainer/analysis）；修复 AC-010 缺口——Rerank web Evidence 持久化从 `research_sources.fetched_at` 穿透写入 `fetched_at_snapshot`（DATABASE.md §6.2），internal 不写该列；AC-010 脚本对迁移态 web 证据按 `research_sources` 回填 URL/获取时间判定。验证：RED 确认（ac_metrics 模块缺失 + fetched_at_snapshot 为 NULL 导致用例失败）；本地全量 unit（非 slow，source 根 .env）929 通过、1 跳过、1 failed（`test_llm` 环境依赖，与本切片无关）、契约 73 项 + `packages/contracts/tests` 131 项 + Architecture 17 项全绿；integration/acceptance 5 项失败与 clean HEAD 失败集一致（既有环境依赖）；docker research-api 容器内对真实 research_db 冒烟：AC-001 100%、AC-010 100% 通过，AC-003/AC-004 对不存在任务 fail-closed 不伪造，AC-003 对真实 completed 任务 100% 通过；新增 `test_ac_metrics` 23 项、`test_rerank_fetched_at` 1 项。
- 各切片实现与验证结果记录见 [CHANGELOG](../CHANGELOG.md)（2026-08-05、2026-08-06、2026-08-07 条目）。


### 范围内工作

- 实现 Knowledge Search Tool 及 Consumer Contract 测试；
- 按来源策略执行内部检索、外部搜索或两者融合；
- 保持 Planning → Search → Fetch → Rerank → Synthesis → Evidence Graph Build → Report Render 阶段顺序；
- 支持对比型、解释型和影响分析型研究任务；
- 区分内部与外部 Evidence，记录外部 URL、获取时间和内部位置；
- 显式表达共识、冲突、证据不足和时效风险；
- 完成任务状态、租约、取消、重试、恢复、幂等与研究 SSE；
- 记录 Token、外部调用、耗时、预算和受控停止原因。

### 必须完成的规范

- `docs/specs/API.md` 中的研究任务、状态、取消、恢复、报告、Evidence 和 Research SSE；
- `packages/contracts/` 中的 Evidence Contract 与 Internal Retrieval Consumer；
- [`services/research/docs/DATABASE.md`](../../services/research/docs/DATABASE.md)；
- [`services/research/docs/RESEARCH_PIPELINE.md`](../../services/research/docs/RESEARCH_PIPELINE.md)；
- 任务生命周期、Evidence Graph、内部知识外发和恢复策略 ADR。

### 主要交付物

- 三类来源策略的研究任务 API 与 Worker；
- Knowledge Search Tool；
- 统一 Evidence Graph 和结构化报告；
- 可恢复的研究任务状态与 Execution Context；
- 研究 SSE、状态快照和轮询降级接口；
- 成本、Trace 和失败审计记录。

### 退出门禁

- `knowledge` 任务只使用用户选择且当前有权访问的内部知识；
- `web` 任务输出带 URL 和获取时间的外部 Evidence；
- `hybrid` 任务在报告中明确区分内部与外部 Evidence；
- 私有文档内容不会自动进入互联网搜索词；
- 冲突来源不会被合成为无条件确定结论；
- 取消后 Worker 不继续产生业务结果；
- 可恢复任务在 Worker 中断后从安全断点继续，且不重复已完成结果；
- [x] PRD AC-001、AC-003、AC-004 和 AC-010 对应验证入口已建立（切片 H，2026-08-07）。

### 本阶段不做

- 不建设通用 Agent 平台、插件市场或工作流编辑器；
- 不将 Chat SSE 与 Research SSE 合并为同一业务协议；
- 不实现报告多人协作、审批或局部重生成；
- 不允许内部文档绕过脱敏、配置和审计直接外发。

## M4：统一 Web、报告与证据联动

### 阶段目标

将知识问答、研究创建、执行过程、历史、报告和 Evidence 复核整合到唯一 React Web 中，使用户不需要理解服务边界即可完成从问题到可追溯结论的完整流程。M0 为保持来源行为只迁入 DocMind Vue 基线；从 Vue 迁移到 React 属于本阶段的受规格与测试约束的前端替换，不得在 M0 静默完成。

### 进入条件

- M2、M3 的外部 API、SSE 和 Evidence Contract 已稳定；
- 统一导航、路由、页面状态和 Design Token 已形成专项规范；
- 内部 Evidence 原文访问的实时权限复核接口可用。

### 范围内工作

- 建立统一登录、导航、知识中心、据见问答、据见研究、报告、Evidence 面板和管理入口；
- 建立 `knowledge`、`web`、`hybrid` 来源范围与数据使用说明；
- 展示研究阶段、进度、错误、取消、恢复和 SSE 重连状态；
- 建立报告引用与 Evidence 面板双向定位；
- 区分内部文档来源与外部网页来源；
- 打开内部原文时重新校验当前权限；
- 保持 Chat SSE 与 Research SSE 的独立事件解析器和状态机；
- 使用统一 `--es-*` Design Token 和无障碍交互基线。

### 必须完成的规范

- `apps/web/docs/FRONTEND.md`；
- `apps/web/docs/UIDESIGN.md`；
- `docs/specs/API.md` 中供前端消费的认证、问答、研究、报告和治理接口；
- 引用交互、权限复核、错误恢复和 SSE 重连相关测试场景。

### 主要交付物

- 单一 React + TypeScript Web Application；
- 统一身份与导航体验；
- 知识问答、研究创建、运行、历史和报告页面；
- 报告—引用—Evidence 双向联动；
- 前端 API 模块、TanStack Query 服务端状态和两套 SSE 状态机；
- 页面、组件和关键端到端测试。

### 退出门禁

- 用户可从统一入口完成登录、知识问答和三类研究任务；
- 页面刷新或 SSE 断开不会使已持久化任务丢失，且可恢复状态展示正确；
- 报告中的每个引用可定位对应 Evidence；
- 权限被撤销后，历史报告引用仍可显示，但受限内部原文无法继续展开；
- 来源范围、数据外发差异、预计资源等级和受控停止原因使用业务语言说明；
- 前端不存在绕过 `api/` 封装的直接请求或硬编码视觉 Token；
- PRD 的统一品牌、导航、报告可用性和 Evidence 联动 P0 均有端到端用例。

### 本阶段不做

- 不合并两个后端服务；
- 不发展为报告模板市场；
- 不实现多人编辑、评论审批或外部客户门户；
- 不向普通用户展示或承诺模型隐藏推理内容。

## M5：治理、可观察性和部署验收

### 阶段目标

补齐试点发布所需的用户、内容和任务治理，以及日志、指标、Trace、备份、恢复、资源限制和回滚能力，形成在 2 vCPU / 2 GB RAM 环境中可诊断、可恢复的部署基线。

### 进入条件

- M1—M4 的核心业务链路可联调；
- 管理操作、敏感操作和任务成本字段已有稳定数据来源；
- Compose、Nginx、数据卷和独立队列边界可用。

### 范围内工作

- 用户启用/禁用、内容治理、任务查看和基础管理操作；
- 请求 ID、用户 ID、任务 ID、阶段、错误码和耗时的结构化日志；
- 文档入库、检索、研究、队列、错误、Token 和外部调用指标；
- Knowledge Trace、Research Trace 和跨服务请求关联；
- 容器健康检查、启动顺序、资源上限、队列背压和受控降级；
- MySQL、Redis、上传文件、向量索引和 Beat 状态的备份恢复；
- Schema 迁移、兼容发布、失败回滚和恢复演练。

### 必须完成的规范

- `docs/specs/API.md` 中的管理和审计接口；
- 两个服务的 Database、运维和测试规范；
- `docs/CHANGELOG.md`；
- 部署、备份恢复、监控、容量和数据迁移相关 ADR 或专项方案。

### 主要交付物

- 基础管理中心和权限受控的治理 API；
- 结构化日志、核心指标和 Trace 关联；
- 默认轻量、可选增强的监控配置；
- 健康检查、备份、恢复、发布和回滚脚本；
- 2C2G 容量、背压、异常和恢复验收记录。

### 退出门禁

- 管理员可禁用用户、查看任务并审计敏感治理操作；
- 普通日志、前端和导出报告不泄露密码、Token、密钥或内部异常；
- 2C2G 环境下核心 API、数据服务和低并发任务保持可用；
- 达到资源或预算上限时任务排队或受控停止，不通过无限并发换吞吐；
- MySQL 和受管文件卷可以从备份恢复，并完成实际演练；
- 发布、迁移失败和应用回滚均有可重复验证步骤；
- 成本、任务运行和核心错误均可通过日志、指标或 Trace 定位。

### 本阶段不做

- 不承诺多节点高可用、自动故障转移或跨地域灾备；
- 不把完整 Prometheus、Grafana、Loki 套件设为 2C2G 默认常驻服务；
- 不迁移到 Kubernetes；
- 不提前建设多租户计费或商业化运营系统。

## M6：v1.0 发布门禁与后续演进

### 阶段目标

用统一证据确认全部 P0、非功能要求、成功指标和端到端场景达到 v1.0 发布条件，完成安全、兼容、迁移、回滚和文档一致性审查，并将 P1/P2 与当前发布范围明确分离。

### 进入条件

- M0—M5 均满足各自退出门禁；
- 候选版本、评估集、环境和测试数据已冻结；
- 所有未解决问题均有严重级别、影响范围和处置结论。

### 范围内工作

- 执行 PRD §12 的 AC-001—AC-010；
- 执行 PRD §13 的十个端到端验收场景；
- 执行权限矩阵、安全、隐私、恢复、容量和回滚审查；
- 执行两个服务、统一 Web、Contract 和 Compose 的候选版本回归；
- 核对 PRD、架构、API、Contract、Database、Pipeline、Frontend、UI、ROADMAP 和 CHANGELOG；
- 形成已知限制、试点操作手册和发布/回滚决策记录。

### 必须完成的规范

- `docs/specs/PRD.md`、`docs/specs/ARCHITECTURE.md` 与本路线图；
- `docs/specs/API.md`、`packages/contracts/` 和全部服务专项规范；
- `docs/CHANGELOG.md` 与必要 ADR；
- 测试结果、评估报告、恢复演练和发布检查清单。

### 主要交付物

- v1.0 候选版本与不可变构建标识；
- AC-001—AC-010 实际验证记录；
- 十个端到端场景的实际结果；
- 安全、权限、容量、备份恢复和回滚验收记录；
- 发布说明、已知限制和试点运维说明。

### 退出门禁

- PRD §10.1 的全部 P0 均有实现、测试和可追溯规范；
- PRD §12 的全部成功指标达到目标，或由负责人明确拒绝发布；
- PRD §13 的十个端到端场景全部通过；
- 内部证据不存在已知越权路径；
- 候选版本受影响模块回归测试全部通过；
- 备份恢复和应用回滚在候选环境中完成实际演练；
- 文档不存在相互冲突的权威定义、失效链接或未处理占位符；
- 发布负责人完成 Go/No-Go 决策并留存记录。

### 本阶段不做

- 不因接近发布而把未验收 P1 能力并入 v1.0；
- 不以“已知问题”名义接受权限绕过、数据丢失或不可回滚风险；
- 不用历史测试记录代替候选版本的实际验证；
- 不把 P2 方向写成已承诺交付范围。

## 3. 跨阶段依赖与可并行工作

- M0 是后续所有实现阶段的仓库和构建基础。
- M1 的身份、服务认证和 Contract 是 M2 Internal Retrieval 的硬前置。
- M2 的 Knowledge 稳定化工作可与 M1 的非契约部分并行，但 Internal Retrieval 生产实现必须等待 Contract 确认。
- M3 的外部研究 Pipeline 稳定化可提前开展；`knowledge` 与 `hybrid` 接入必须等待 M2 Provider 通过契约测试。
- M4 的信息架构、静态页面和 Design Token 可提前设计，真实联调必须基于 M2、M3 的稳定 API、SSE 和 Evidence Contract。
- 日志、指标、成本和恢复测试应随 M1—M4 持续接入；M5 负责形成完整发布门禁，不代表此前可以忽略可观察性。
- M6 只做候选版本验收、修复和发布决策，不承接未完成的大型架构改造。

任何并行工作都不得绕过“规范 → 验收条件与测试 → 实现 → 验证”的进入门禁。

## 4. 专项规范编写顺序

后续文档按依赖顺序编写：

1. `docs/plans/MONOREPO_MIGRATION_PLAN.md`：先建立不改变业务行为的代码布局、构建和部署骨架；
2. `docs/specs/IDENTITY_AND_ACCESS.md`：定义 JWT Claims、令牌生命周期、用户禁用、服务凭证、授权上下文和敏感数据外发策略；
3. `docs/specs/API.md`：定义 `/api/v1/*` 与 `/internal/v1/*` 协议表面、错误语义、幂等、分页和两类 SSE；
4. [`packages/contracts/`](../../packages/contracts/README.md)：在 API 语义稳定后固化 Internal Retrieval、Evidence、错误、版本与固定样例；
5. [`services/knowledge/docs/DATABASE.md`](../../services/knowledge/docs/DATABASE.md) 与 [`RAG_PIPELINE.md`](../../services/knowledge/docs/RAG_PIPELINE.md)：定义 Knowledge 数据和 Internal Retrieval Provider；
6. [`services/research/docs/DATABASE.md`](../../services/research/docs/DATABASE.md) 与 [`RESEARCH_PIPELINE.md`](../../services/research/docs/RESEARCH_PIPELINE.md)：定义 Research 数据、Contract Consumer、研究状态、Evidence Graph 和报告生成；
7. `apps/web/docs/FRONTEND.md` 与 `UIDESIGN.md`：在稳定 API、SSE 和 Evidence Contract 基础上定义统一路由、页面、状态机、引用交互、Design Token 和可访问性；
8. [`docs/specs/DATA_MIGRATION_AND_ROLLBACK.md`](../specs/DATA_MIGRATION_AND_ROLLBACK.md)：定义生产源数据映射、停机窗口、双边校验、恢复与回滚；
9. [`docs/specs/TESTING.md`](../specs/TESTING.md)：汇总环境矩阵、契约与端到端用例、性能基线、恢复演练和发布门禁。

`docs/CHANGELOG.md` 与 `docs/decisions/` 随以上规范和实现持续维护，不在最后一次性补写。同一技术事实只在一个权威文档中定义；其他文档必须使用交叉引用。

## 5. v1.x 与远期演进

### 5.1 v1.x（P1）

v1.0 通过发布门禁后，以下能力分别进入独立规格、验收和实施周期：

- 多 KB 企业知识问答；前端选择器保留扩展形态，当前只允许单选并提示“规划中”；
- 跨任务 Evidence 发现和复用；
- 报告版本与局部重新生成；
- PDF/Word 正式导出；
- Excel/CSV 文档入库与可检索态（结构化转 MD 分块），扩展 FR-KB-002 支持格式；
- 更完整的使用、质量和成本看板；
- 更丰富的报告模板，但不发展为模板市场。

### 5.2 远期（P2）

以下方向只保留产品演进位置，不进入 v1.0 或默认 v1.x 承诺：

- 指定用户共享、部门空间和完整 ACL；
- 企业 SSO、SAML 和 SCIM；
- 报告协作审批和多人编辑；
- 通用 Agent、插件和工作流市场；
- 执行通道（Execution Lane）：Chat 意图路由到整文件执行的执行器契约，首个执行器为 excel-ai-analyst（公式校验/勾稽/推演）；作为「通用 Agent、插件和工作流市场」的早期形态，不提前建设平台；
- 面向外部客户的多租户商业化能力。

### 5.3 基础设施演进触发条件

当持续内存压力、队列等待、单机故障风险、备份恢复目标或试点规模超过总体架构基线时，按 `docs/specs/ARCHITECTURE.md` §16 评估主机升级、数据服务拆分、共享存储、水平扩展和 Kubernetes。演进不得静默改变外部 API、Internal Retrieval 或 Evidence Contract 语义。

## 6. 路线图维护规则

- 状态更新必须引用实际测试、评审、评估、演练或发布记录；
- 阶段只有在全部退出门禁满足后才能标记为“已完成”；
- “受阻”必须记录阻塞条件、影响范围、责任边界和解除条件；
- 产品范围变化先更新 PRD，系统边界变化先更新 ARCHITECTURE，公共契约变化先更新 API/Contract；
- 影响跨服务边界、权限、安全、数据生命周期或兼容性的变化必须评估 ADR；
- ROADMAP 变化同步记录到 `docs/CHANGELOG.md`；
- 禁止在本文件记录未经实际验证的 PASS、完成比例或发布日期承诺。

## 7. 相关文档

- [产品需求文档](../specs/PRD.md)
- [总体技术架构与部署拓扑](../specs/ARCHITECTURE.md)
- [Monorepo 迁移实施计划](MONOREPO_MIGRATION_PLAN.md)
- `docs/specs/IDENTITY_AND_ACCESS.md` — 统一身份、授权、服务凭证和敏感数据外发规范
- `docs/specs/API.md` — 外部与内部 API、错误码和 SSE 协议
- [`packages/contracts/`](../../packages/contracts/README.md) — Internal Retrieval、Evidence、错误、版本与固定 Fixture 契约
- [`services/knowledge/docs/DATABASE.md`](../../services/knowledge/docs/DATABASE.md) — Platform 与 Knowledge 数据、索引、生命周期和迁移边界
- [`services/knowledge/docs/RAG_PIPELINE.md`](../../services/knowledge/docs/RAG_PIPELINE.md) — 入库、检索、Chat 与 Internal Retrieval Pipeline
- [`services/research/docs/DATABASE.md`](../../services/research/docs/DATABASE.md) — Research Service 数据库设计
- [`services/research/docs/RESEARCH_PIPELINE.md`](../../services/research/docs/RESEARCH_PIPELINE.md) — Research Pipeline
- [`apps/web/docs/FRONTEND.md`](../../apps/web/docs/FRONTEND.md) — 页面、交互和状态机
- [`apps/web/docs/UIDESIGN.md`](../../apps/web/docs/UIDESIGN.md) — Design Token 和视觉规范
- [开发指南](../guides/DEVELOPMENT.md) — 环境、目录结构、命令和 SDD 工作流
- [生产数据迁移、校验和回滚](../specs/DATA_MIGRATION_AND_ROLLBACK.md)
- [测试策略、环境矩阵和发布验收](../specs/TESTING.md)
- [配置规范](../specs/CONFIGURATION.md)
- [数据保留与清理](../specs/DATA_RETENTION.md)
- [部署与运维](../specs/OPERATIONS.md)
- [产品与实现变更记录](../CHANGELOG.md)
- [架构决策记录](../decisions/README.md)
