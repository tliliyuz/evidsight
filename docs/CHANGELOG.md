# Changelog

本文记录 EvidSight 产品规范、架构、契约和实现的可审查变化。格式参考 Keep a Changelog；“已确认设计”不等同于“已经实现或发布”。

## [Unreleased]

### Added

- 建立 EvidSight PRD、总体架构、身份与访问、API、Database、Knowledge/Research Pipeline、Frontend 和 UI 规范基线。（2026-08-01）
- 建立 Monorepo 迁移计划、开发指南、测试策略、配置、数据保留、运维及数据迁移回滚规范。（2026-08-01）
- 建立重要架构决策记录目录。（2026-08-01）
- 完成 DocMind 后端与前端、ResearchMind 后端的 M0 Monorepo 结构迁移，并保留可审查的来源提交与 Git 历史；验收证据见 [`migration/MIGRATION_ACCEPTANCE.md`](migration/MIGRATION_ACCEPTANCE.md)。（2026-08-02）

### Changed

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

### Not Yet Implemented

- External OpenAPI、Internal Contract JSON Schema、Fixture 和生成物尚未落地。（2026-08-01）
- 本条目不声明统一身份、Internal Retrieval、Research 前端并入统一 Web、生产数据迁移或 v1.0 发布验收已经完成。（2026-08-02）

## 维护规则

- 行为、权限、状态机、公共契约和数据生命周期变化必须在同一变更中更新本文件。
- `[Unreleased]` 下每个一级变更条目必须标注实际改动日期，格式为 `（YYYY-MM-DD）`；不得只依赖版本发布日期。
- 只记录实际合并的事实；测试结果和迁移证据分别进入 `docs/specs/TESTING.md` 与 `docs/migration/MIGRATION_ACCEPTANCE.md`。
- 发布版本使用 `MAJOR.MINOR.PATCH`，并标注日期、迁移要求、兼容窗口和已知限制。
