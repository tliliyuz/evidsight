# EvidSight 操作指南索引

本目录只说明“如何执行”，不定义产品行为、架构边界、接口、权限、数据生命周期或发布门禁。任何指南与 `docs/specs/` 冲突时，以对应权威规范为准并按 [文档治理指南](DOCUMENT_GOVERNANCE.md) 处理。

| 主题 | 指南 | 对应权威来源 |
|:---|:---|:---|
| 开发环境、目录与工作流 | [DEVELOPMENT.md](DEVELOPMENT.md) | 根 `AGENTS.md` 与任务对应规范 |
| 测试命令与发布记录 | [TEST_EXECUTION.md](TEST_EXECUTION.md) | [测试与发布验证规范](../specs/TESTING.md) |
| 三节点部署、备份与恢复操作 | [OPERATIONS.md](OPERATIONS.md) | [总体架构](../specs/ARCHITECTURE.md)、[运行可靠性与恢复规范](../specs/RELIABILITY.md) |
| 文档归属与冲突裁决 | [DOCUMENT_GOVERNANCE.md](DOCUMENT_GOVERNANCE.md) | 根 `AGENTS.md`、[ADR 治理规则](../decisions/README.md) |

指南中的命令、顺序和模板可以随工具链调整；若调整会改变系统必须满足的结果、信任边界、数据语义或发布门禁，必须先修改对应规范并重新执行 ADR 检查。
