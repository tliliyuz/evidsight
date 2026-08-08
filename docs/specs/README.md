# EvidSight 权威规范索引

本目录集中项目级、具有约束力的规范。规范回答“系统必须是什么、允许什么、如何验收”；执行方法见 [`guides/`](../guides/README.md)，阶段安排与迁移步骤见 [`plans/`](../plans/ROADMAP.md)，重要选择的历史原因见 [`decisions/`](../decisions/README.md)。

## 规范清单

| 主题 | 权威文档 | 主要边界 |
|:---|:---|:---|
| 产品 | [`PRD.md`](PRD.md) | 定位、用户、范围、功能、权限矩阵和产品验收 |
| 总体架构 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | 服务边界、数据所有权、部署拓扑和系统级非功能要求 |
| 身份与访问 | [`IDENTITY_AND_ACCESS.md`](IDENTITY_AND_ACCESS.md) | 认证、令牌、服务身份、授权上下文和敏感数据外发 |
| API 与事件 | [`API.md`](API.md) | 外部/内部 HTTP、错误语义、幂等、版本和 SSE |
| 配置 | [`CONFIGURATION.md`](CONFIGURATION.md) | 配置键、所有者、类型、默认值和安全级别 |
| 测试 | [`TESTING.md`](TESTING.md) | 测试矩阵、契约验证、端到端场景和发布门禁 |
| 数据迁移 | [`DATA_MIGRATION_AND_ROLLBACK.md`](DATA_MIGRATION_AND_ROLLBACK.md) | 生产数据映射、校验、切换和回滚 |
| 数据保留 | [`DATA_RETENTION.md`](DATA_RETENTION.md) | 数据保留、清理、保全和引用闭包 |
| 运行可靠性与恢复 | [`RELIABILITY.md`](RELIABILITY.md) | 服务目标、健康、容量、备份恢复门禁和故障语义 |

## 阅读顺序

1. 先读 PRD 确认范围和验收目标。
2. 再读总体架构和身份规范确认服务与安全边界。
3. 按任务读取 API、配置、测试、数据迁移、保留或可靠性规范。
4. 涉及具体模块时继续读取该模块的 Database、Pipeline、Frontend 或 Contract 文档。

部署、备份、恢复和测试的实际执行方法位于 [`guides/`](../guides/README.md)，不得反向定义或覆盖本目录规范。

规范冲突时，以主题对应的唯一权威文档为准；如果两个主题的权威文档相互冲突，应先修订规范或新增 ADR，不得由实现自行选择。
