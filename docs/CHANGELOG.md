# Changelog

本文记录 EvidSight 产品规范、架构、契约和实现的可审查变化。格式参考 Keep a Changelog；“已确认设计”不等同于“已经实现或发布”。

## [Unreleased]

### Added

- 建立 EvidSight PRD、总体架构、身份与访问、API、Database、Knowledge/Research Pipeline、Frontend 和 UI 规范基线。
- 建立 Monorepo 迁移计划、开发指南、测试策略、配置、数据保留、运维及数据迁移回滚规范。
- 建立重要架构决策记录目录。

### Changed

- 将项目级文档分为 `specs/`、`guides/`、`plans/`、`decisions/` 与迁移证据层，并新增文档中心和权威规范索引；模块专项文档继续跟随模块维护。
- 明确 v1.0 Chat 只绑定单个知识库；前端保留可演进选择器，但多选不可执行并提示“多知识库问答规划中”。
- 多 KB 能力仅用于 Research 通过权限感知的 Internal Retrieval 检索；多 KB Chat 延后至 v1.x。
- 统一 Research 七阶段顺序为 Planning → Searching → Fetching → Reranking → Synthesizing → Evidence Graph Build → Rendering。
- Internal Evidence 身份增加稳定 `document_version_id`，用于重处理后的历史来源追溯。
- 明确 M0 保留 Vue 来源迁移基线，M4 按前端专项规范交付唯一 React + TypeScript Web。

### Not Yet Implemented

- DocMind 与 ResearchMind 生产代码和历史尚未完成 M0 迁入。
- External OpenAPI、Internal Contract JSON Schema、Fixture 和生成物尚未落地。
- 本条目不声明统一身份、Internal Retrieval、统一 Web 或 v1.0 已经可运行。

## 维护规则

- 行为、权限、状态机、公共契约和数据生命周期变化必须在同一变更中更新本文件。
- 只记录实际合并的事实；测试结果和迁移证据分别进入 `docs/specs/TESTING.md` 与 `docs/migration/MIGRATION_ACCEPTANCE.md`。
- 发布版本使用 `MAJOR.MINOR.PATCH`，并标注日期、迁移要求、兼容窗口和已知限制。
