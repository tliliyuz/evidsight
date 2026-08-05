# EvidSight Agent 指南

本文件只定义 Agent 的开发入口、规范驱动开发（SDD）门禁和文档导航。产品、架构、接口及代码审查细则以对应权威文档为准，不在此重复定义。

## 规范驱动开发（SDD）

任何业务行为必须先由可审查的规范定义，再由测试转化为可执行验收条件，最后才允许编写生产实现。

- 规范是开发输入，不是实现完成后的补充说明。
- 规范缺失、冲突或无法导出明确验收条件时，暂停实现并先澄清。
- 同一事实只在一个权威文档中定义；其他位置只交叉引用。
- 不得根据既有实现反向编写规范或测试。
- 发现实现、测试和规范不一致时，先按 [文档治理指南](docs/guides/DOCUMENT_GOVERNANCE.md) 完成事实取证、冲突分类和负责人裁决；不得用普通实施授权替代文档裁决。

### 开发门禁

新功能、Bug 修复和行为变更必须遵循：

```text
ADR 检查与裁决
  → 规格确认
  → 验收条件与测试场景
  → RED：先写测试并确认因目标行为缺失而失败
  → GREEN：编写使测试通过的最小实现
  → REFACTOR：在持续绿灯下整理设计
  → 受影响模块完整验证
  → 权威文档与变更记录同步
  → 代码审查
```

- 新功能、Bug 修复、行为变更和架构调整必须先按 [ADR 治理规则](docs/decisions/README.md) 执行 ADR 检查；命中时在该规则规定的解除条件满足前，不得继续规格、测试或实现。
- 没有明确规格，不写测试和生产代码。
- 没有从规格导出的验收测试，不写生产代码。
- 没有亲自观察到正确的 RED，不进入 GREEN。
- RED 若源于语法、Fixture、环境或 Mock 错误，先修正测试。
- GREEN 只实现当前验收条件要求的最小行为。
- 只有相关测试全部通过后才允许重构。
- 完成声明必须附本次实际执行的验证命令和结果。

纯文档、注释、生成物或无法直接制造业务 RED 的配置变更，应说明例外理由，并执行适用的格式、链接、Schema、生成器或 smoke 验证。其他例外必须在修改生产代码前获得负责人明确批准。

## 权威文档矩阵

项目级规范统一收录在 `docs/specs/`，完整分层与导航见 `docs/README.md`。开始任务前，按变更范围读取对应文档；目标文档尚未建立时，先补齐规范，不得在无规范情况下推断设计。

| 主题 | 唯一权威来源 |
|---|---|
| 产品定位、用户、范围、功能与验收 | `docs/specs/PRD.md` |
| 总体架构、服务边界与部署拓扑 | `docs/specs/ARCHITECTURE.md` |
| 身份、权限与数据访问策略 | `docs/specs/IDENTITY_AND_ACCESS.md` |
| 外部/内部 API、错误码与 SSE | `docs/specs/API.md` |
| 跨服务请求、事件与 Evidence Contract | `packages/contracts/` |
| 数据库、索引、外键与迁移 | 各服务的 `docs/DATABASE.md` |
| Knowledge RAG Pipeline | `services/knowledge/docs/RAG_PIPELINE.md` |
| Research Agent Pipeline | `services/research/docs/RESEARCH_PIPELINE.md` |
| 前端页面、交互与状态机 | `apps/web/docs/FRONTEND.md` |
| Design Token 与组件样式 | `apps/web/docs/UIDESIGN.md` |
| Monorepo 迁移约束 | `docs/plans/MONOREPO_MIGRATION_PLAN.md` |
| 开发环境、目录、命令与工作流 | `docs/guides/DEVELOPMENT.md` |
| 文档归属、冲突裁决与状态治理 | `docs/guides/DOCUMENT_GOVERNANCE.md` |
| 测试矩阵与发布验证 | `docs/specs/TESTING.md` |
| 配置键与运行边界 | `docs/specs/CONFIGURATION.md` |
| 数据迁移、校验与回滚 | `docs/specs/DATA_MIGRATION_AND_ROLLBACK.md` |
| 数据保留与清理 | `docs/specs/DATA_RETENTION.md` |
| 部署、备份、恢复与故障处理 | `docs/specs/OPERATIONS.md` |
| 阶段目标与排期 | `docs/plans/ROADMAP.md` |
| 行为变更记录 | `docs/CHANGELOG.md` |
| 重要架构决策 | `docs/decisions/ADR-NNN.md` |
| 代码审查流程与检查项 | `.claude/commands/review.md` |

当文档冲突或实现领先于规范时，不自行选择方便实现的一方：先按 [文档治理指南](docs/guides/DOCUMENT_GOVERNANCE.md) 输出文档裁决候选并取得有效裁决。涉及重要设计取舍时，按 [ADR 治理规则](docs/decisions/README.md) 执行 ADR 检查与裁决，不得由实现自行决定是否需要 ADR。

## 工作约束

- 只修改当前任务和已确认规范覆盖的范围，不提前实现后续 Phase。
- 背景与进入条件核验以权威文档状态为准（ROADMAP 阶段记录、CHANGELOG、对应 spec），不通过运行测试判断；未先阅读相关权威文档不得开始实现。
- 验证节奏遵循「开发前不测、开发中不测、开发结束不重复测」：测试只在 SDD 门禁要求的点执行（RED 确认、受影响模块完整验证）。RED 正常失败不反馈；仅 RED 异常（目标行为缺失之外的失败、本应失败却通过）时反馈负责人。
- macOS 开发与验证一律使用 docker 全栈（compose）环境；不使用本机 venv 对依赖外部服务的测试套件单独跑验。
- 代码审查使用 `/review`；评审清单、严重级别和输出格式以 `.claude/commands/review.md` 为准。
- 新增依赖前说明用途、维护状态、体积和替代方案。
- 注释、项目文档和提交信息使用中文；代码标识符遵循语言社区惯例使用英文。
- 未经负责人明确批准，不得新增或固化权威文档；临时规格、计划、验收记录等只能放入 Git 忽略目录且不得提交，任务结束后删除。Skill 或工具流程不得绕过此约束。
- 更新 `docs/CHANGELOG.md` 时，每个一级变更条目必须标注实际改动日期 `（YYYY-MM-DD）`。
- 未经负责人针对当前操作的明确授权，只允许执行只读 Git 命令；不得修改工作区、索引、引用或远端状态。批准设计、开始任务或完成修改不等于授权 Git 写操作。
- 经授权创建提交时，subject 必须使用 `add|fixed|update|refactor: 中文描述`；技术专有名词可保留英文。
