# Changelog

本文记录 EvidSight 产品规范、架构、契约和实现的可审查变化。格式参考 Keep a Changelog；“已确认设计”不等同于“已经实现或发布”。

## [Unreleased]

### Added

- 建立 EvidSight PRD、总体架构、身份与访问、API、Database、Knowledge/Research Pipeline、Frontend 和 UI 规范基线。（2026-08-01）
- 建立 Monorepo 迁移计划、开发指南、测试策略、配置、数据保留、运维及数据迁移回滚规范。（2026-08-01）
- 建立重要架构决策记录目录。（2026-08-01）
- 完成 DocMind 后端与前端、ResearchMind 后端的 M0 Monorepo 结构迁移，并保留可审查的来源提交与 Git 历史。（2026-08-02）
- 建立 M1 统一身份、服务认证与敏感数据外发策略 ADR 候选，进入 M1 规范与验收准备。（2026-08-02）
- 为 Knowledge 既有用户增加稳定 Platform User UUID，并将 Research Task 用户归属改为无跨库外键的 UUID。（2026-08-02）

### Updated

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
