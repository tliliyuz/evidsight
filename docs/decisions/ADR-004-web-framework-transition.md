# ADR-004：M0 Vue 迁移基线与 M4 React 目标

- 状态：accepted
- 日期：2026-08-01

## 背景

DocMind 的现有前端是 Vue 3。M0 要求保留来源历史和迁移前后行为等价，不能同时实施框架替换；新的 EvidSight 前端专项规范基于 React + TypeScript、React Router 和 TanStack Query，服务于统一研究、报告和 Evidence 交互。

## 决策

- M0 将 DocMind Vue 前端原样迁入 `apps/web`，只做仓库和构建标识规范化。
- M0 验收只证明 Vue 来源基线迁移等价，不代表 v1.0 前端完成。
- M4 在外部 API、SSE 和 Evidence Contract 稳定后，将唯一 Web 替换为 React + TypeScript 实现。
- M4 必须使用前端专项验收和端到端测试证明功能等价或符合新 PRD，不长期并存两套可运行前端。

## 后果

项目会经历明确的临时 Vue 基线，但避免把框架重写夹带进历史迁移。M4 需要单独的迁移规格、页面映射、测试迁移和删除旧实现门禁。

## 被否决方案

- 在 M0 直接重写 React：无法证明迁移前后行为等价，也混淆历史导入与产品开发。
- 长期保留 Vue/React 双前端：增加协议漂移、测试和部署成本，违反唯一 Web 边界。

## 重新评估触发条件

如果 M4 开始前 React 迁移成本超过已批准预算，必须用新的前端专项评估和 ADR 决定是否调整目标；不得仅修改实现而保留冲突文档。

## 相关规范

- [Monorepo 迁移计划](../plans/MONOREPO_MIGRATION_PLAN.md)
- [路线图](../plans/ROADMAP.md)
- [Frontend](../../apps/web/docs/FRONTEND.md)
