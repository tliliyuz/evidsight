# 据见（EvidSight）

据见是面向企业内部研究场景的证据驱动知识与深度研究平台。它将企业知识问答、互联网研究、Evidence Graph 和结构化报告放在统一身份、权限和审计边界内，使关键结论可以回到证据，再回到原始来源位置。

> 当前状态：规范基线与 Monorepo 迁移准备阶段。仓库已经建立产品、架构、接口、数据库、Pipeline 和前端设计，DocMind/ResearchMind 的生产实现尚未完成迁入；根目录示例 CLI 不代表 EvidSight 产品已经可运行。

## v1.0 范围

- 单 KB 企业知识问答与会话；前端保留可演进选择器，多选显示“规划中”且不可执行；
- `knowledge`、`web`、`hybrid` 三类深度研究来源策略；
- Research 通过权限感知的 Internal Retrieval 使用一个或多个 KB；
- 内外来源区分、Evidence Graph、冲突与不确定性表达；
- 结构化报告及引用—Evidence—原始来源联动；
- 统一身份、实时权限复核、治理审计和可恢复任务。

多 KB Chat、正式 PDF/Word 导出、跨任务 Evidence 复用和完整成本看板属于 v1.x。

## 仓库导航

| 入口 | 内容 |
|:---|:---|
| [文档中心](docs/README.md) | 文档分层、规范索引和维护规则 |
| [开发指南](docs/guides/DEVELOPMENT.md) | 环境、目录结构、启动、测试和开发工作流 |
| [PRD](docs/specs/PRD.md) | 产品范围、角色、功能和验收指标 |
| [总体架构](docs/specs/ARCHITECTURE.md) | 服务边界、部署拓扑、数据隔离和恢复目标 |
| [身份与访问](docs/specs/IDENTITY_AND_ACCESS.md) | JWT、用户禁用、服务认证、权限与敏感数据外发 |
| [API](docs/specs/API.md) | HTTP、错误码、幂等和两类 SSE |
| [跨服务契约](packages/contracts/README.md) | Internal Retrieval 与 Evidence Contract |
| [Knowledge Pipeline](services/knowledge/docs/RAG_PIPELINE.md) | 入库、单 KB Chat、多 KB Internal Retrieval |
| [Research Pipeline](services/research/docs/RESEARCH_PIPELINE.md) | 七阶段研究、恢复、Evidence Graph 和报告发布 |
| [前端设计](apps/web/docs/FRONTEND.md) | 页面、交互和客户端状态机 |
| [路线图](docs/plans/ROADMAP.md) | M0—M6 里程碑与退出门禁 |

## 当前开发入口

当前应先执行 [Monorepo 迁移计划](docs/plans/MONOREPO_MIGRATION_PLAN.md)。在 M0 验收完成前，不应把根目录 `uv run evidsight`、空的服务目录或原型页面描述为可发布能力。

开发行为遵循 [AGENT.md](AGENTS) 的规范驱动开发门禁：先确认权威规范和验收条件，再写测试与实现，最后同步文档和变更记录。

## M0 Monorepo 开发入口

M0 按 [总体架构](docs/specs/ARCHITECTURE.md)、[PRD](docs/specs/PRD.md) 和 [迁移计划](docs/plans/MONOREPO_MIGRATION_PLAN.md) 将两个来源项目迁入以下独立边界：

```text
apps/web/                 # M0 阶段的统一 Web 基线
services/knowledge/       # Knowledge Service，独立 Python 环境与迁移链
services/research/        # Research Service，独立 Python 环境与迁移链
packages/contracts/       # 跨服务纯数据契约
packages/frontend-shared/ # 经验证后才能进入的前端共享能力
```

本地开发需要 Python 3.12、Node.js 20+、Docker Engine、Docker Compose v2 和 Git。迁移完成后，两个后端分别在自己的服务目录创建 `.venv` 并安装各自 `requirements.txt`；Web 严格使用 `apps/web/package-lock.json` 安装依赖。根目录不合并两个服务的运行时依赖。

根验证入口：

```bash
make test
make test-knowledge
make test-research
make test-web
make build-web
make compose-config
```

在对应来源代码完成迁入前，这些命令只表示已经建立的目标入口，不代表服务当前可运行。

## License

许可证见后续迁移保留的项目授权文件；正式发布前必须完成来源项目许可证兼容复核。
