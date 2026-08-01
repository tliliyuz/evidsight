# 架构决策记录

本目录记录会长期影响服务边界、安全、数据生命周期、公共契约或兼容性的决策。

每份 ADR 使用状态 `proposed|accepted|superseded|deprecated`，包含背景、决策、后果、被否决方案、重新评估触发条件和相关规范。已接受 ADR 不因实现尚未完成而失效；实现偏离时必须先修订或替代 ADR。

## 索引

- [ADR-001：v1.0 单 KB Chat 与多 KB Research 边界](ADR-001-single-kb-chat.md)
- [ADR-002：双服务数据所有权与 Internal Retrieval 边界](ADR-002-service-boundary.md)
- [ADR-003：内部 Evidence 不持久化正文](ADR-003-internal-evidence-no-content.md)
- [ADR-004：M0 Vue 迁移基线与 M4 React 目标](ADR-004-web-framework-transition.md)
