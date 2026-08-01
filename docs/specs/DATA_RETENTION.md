# DATA RETENTION — 数据保留与清理规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 治理基线 |
| 最后更新 | 2026-08-01 |

## 1. 原则

- 业务事实、缓存、审计和临时正文分别治理；
- 保留期限使用 [CONFIGURATION.md](CONFIGURATION.md) 注册的配置键；生产覆盖默认值时必须留下治理记录；
- 清理任务幂等、可审计、可限速，不破坏引用闭包；
- 法规或调查保全覆盖普通清理，但必须有范围、原因和解除记录；
- 删除正文不等于删除最小引用元数据。

## 2. 数据类别

| 数据 | 基线语义 |
|:---|:---|
| Internal `minimal_excerpt` | 不持久化，只存在当前 Research Step 内存 |
| Knowledge 上传与 Active Version | 随文档生命周期；删除遵循可恢复清理 |
| 历史 Document Version | 按配置清理；保留稳定 ID 和失效语义 |
| Internal Evidence Reference | 随 Task/Report 保留，不授予原文权限 |
| Web 正文 | 默认 7 天；由 `EVIDSIGHT_RESEARCH_WEB_CONTENT_TTL_SECONDS` 控制，到 `content_expires_at` 清空 |
| Web URL/获取元数据 | 随 Task 保留，用于审计引用 |
| published Report Revision | 随 Task 保留且不可变 |
| failed/building Revision | 默认 30 天；由 `EVIDSIGHT_RESEARCH_FAILED_REVISION_TTL_SECONDS` 控制 |
| Agent Event/Audit | 默认 365 天；由 `EVIDSIGHT_AUDIT_RETENTION_DAYS` 控制，只含安全摘要 |
| Trace | 默认 30 天；由 `EVIDSIGHT_TRACE_RETENTION_DAYS` 控制，不含正文、Prompt 或隐藏推理 |
| Redis Cache/Lock/Lease | TTL 或业务完成清理；不作为唯一事实 |

## 3. 用户与权限变化

禁用用户不级联删除业务数据，但立即阻止登录、刷新、Chat、任务创建/恢复、Internal Retrieval 和来源展开。重新启用不恢复旧 Token 或旧任务。删除请求必须区分账号禁用、业务数据删除和审计依法保留。

## 4. 清理验证

- 到期正文不可再从数据库、缓存、日志、Trace 或错误恢复；
- 历史报告引用仍能显示允许保留的来源类型、标题和位置摘要；
- 来源展开返回 `restricted|missing|stale`，不降级展示历史正文；
- 清理批次记录范围、数量、失败、重试和请求/任务 ID；
- 备份保留与生产清理策略一致，过期备份也必须安全删除。
