# ADR-001：v1.0 单 KB Chat 与多 KB Research 边界

- 状态：accepted
- 日期：2026-08-01

## 背景

Knowledge 使用 Per-KB Collection 隔离向量和 BM25 生命周期。多 KB Chat 会引入扇出检索、缓存和内存放大、异构分数归一化、索引状态不一致及部分失败语义，并与 2C2G 试点基线冲突。Research 长任务已有预算、状态、降级和完整度机制，可以承担受限的多 KB 检索。

## 决策

- v1.0 Chat 与 Conversation 只绑定一个 KB，请求字段为单数 `knowledge_base_id`。
- 前端保留可演进选择器形态，但当前只能单选；多选入口不可执行并显示“多知识库问答规划中”。
- Research 可通过 `/internal/v1/retrieval/search` 提交 `knowledge_base_ids`，由 Knowledge 逐 KB 实时鉴权、检索并公平合并。
- 客户端不得通过并发多个 Chat 请求模拟多 KB Chat。

## 后果

Chat 数据模型、权限、会话恢复和错误语义保持简单；Research 继续承担复杂检索。前端未来启用多选无需重做主要布局，但必须修改 API、Database、Pipeline、测试和本 ADR。

## 被否决方案

- v1.0 直接支持多 KB Chat：2C2G 下的缓存、扇出和部分失败尚无验收证据。
- 客户端并发多个单 KB Chat：会产生多份答案和不可审计的客户端融合，破坏会话事实源。

## 重新评估触发条件

只有在跨 KB 缓存内存上限、分数归一化、公平合并、索引状态、取消及部分失败语义均有规范和 2C2G 验证后，才评估将多 KB Chat 纳入 v1.x。

## 相关规范

- [PRD](../specs/PRD.md)
- [API](../specs/API.md)
- [Knowledge Pipeline](../../services/knowledge/docs/RAG_PIPELINE.md)
- [Frontend](../../apps/web/docs/FRONTEND.md)
