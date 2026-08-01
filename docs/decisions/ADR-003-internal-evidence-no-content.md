# ADR-003：内部 Evidence 不持久化正文

- 状态：accepted
- 日期：2026-08-01

## 背景

Research 报告需要长期保留来源关系，但用户对内部知识的权限可能撤销，文档也可能重处理或删除。持久化内部摘录会形成绕过 Knowledge 实时权限的副本。

## 决策

- Internal Retrieval 的 `minimal_excerpt` 只存在于当前 Step 的受控内存工作集。
- Research 只持久化 KB、Document、Document Version、Segment 的稳定 ID、显示和位置摘要、时间、评分摘要及有效性状态。
- 日志、Trace、SSE、错误、Evidence、Claim 和 Report 均不得保存内部正文或等价副本。
- 展开内部来源必须调用 Knowledge 来源位置 API，并按当前用户、KB、文档版本和状态重新鉴权。

## 后果

恢复 Rerank/Synthesis 时需要按完整稳定身份精确重取；权限或来源失效时不得替换版本，必要时从 Searching 建立新的候选闭包，因此新 attempt 的结果可能变化。历史报告仍可显示引用元数据，但无权或已清理来源返回 `restricted|missing|stale`。

## 被否决方案

- 将 excerpt 保存在 Evidence/Report：权限撤销后形成绕过路径。
- 只依赖 Research 自己的权限快照：不能反映用户、KB、文档和版本当前状态。
- 永久加密保存正文：密钥和保留生命周期仍扩大泄漏面，v1.0 没有必要。

## 重新评估触发条件

任何短期恢复缓存方案都必须先定义加密、TTL、清理、禁用用户失效和审计，并以新 ADR 替代本决策的相应部分。

## 相关规范

- [身份与访问](../specs/IDENTITY_AND_ACCESS.md)
- [跨服务契约](../../packages/contracts/README.md)
- [Research Pipeline](../../services/research/docs/RESEARCH_PIPELINE.md)
