# EvidSight 文档中心

本目录按“规范、指南、计划、决策、记录”分层。查找项目事实或约束时先进入规范目录；执行开发或迁移工作时再进入指南或计划目录。模块私有设计继续跟随代码放在对应模块的 `docs/` 中。

## 文档分层

| 目录或文件 | 职责 | 内容规则 |
|:---|:---|:---|
| [`specs/`](specs/README.md) | 权威规范 | 定义产品、架构、接口、权限、配置、测试、数据与运行约束；实现不得与其冲突 |
| [`guides/`](guides/DEVELOPMENT.md) | 操作指南 | 说明开发者如何搭建环境、执行命令和遵守交付流程，不重复定义产品行为 |
| [`plans/`](plans/ROADMAP.md) | 路线与实施计划 | 记录阶段顺序、依赖、退出门禁和迁移步骤，不代表功能已实现 |
| [`decisions/`](decisions/README.md) | 架构决策记录 | 记录重要选择、替代方案和后果；不能代替当前规范 |
| [`CHANGELOG.md`](CHANGELOG.md) | 变更记录 | 记录已经发生的可审查变化及尚未实现项 |
| `migration/` | 迁移证据（按计划建立） | 保存基线、来源清单和验收结果，不保存临时进度 |

## 模块专项文档

| 主题 | 权威入口 |
|:---|:---|
| 跨服务数据契约 | [`packages/contracts/README.md`](../packages/contracts/README.md) |
| Knowledge 数据与 RAG | [`services/knowledge/docs/`](../services/knowledge/docs/) |
| Research 数据与 Pipeline | [`services/research/docs/`](../services/research/docs/) |
| Web 页面、交互与视觉 | [`apps/web/docs/`](../apps/web/docs/) |

## 维护规则

1. 同一事实只在一个权威文档中定义，其他文档使用链接引用。
2. 产品、权限、接口、状态机、公共契约或数据生命周期变化，先更新对应规范，再更新测试、实现和 Changelog。
3. 计划中的目标、迁移步骤和占位命令不得表述为已实现能力。
4. 新增长期文档前先判断其应归入规范、指南、计划、决策还是证据；不得把新规范重新堆回 `docs/` 根层。
5. 模块专属数据库、Pipeline、前端规范跟随模块维护；跨模块规则才进入 `docs/specs/`。

