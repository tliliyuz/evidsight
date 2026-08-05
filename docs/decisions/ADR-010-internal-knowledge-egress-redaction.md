# ADR-010：内部知识外发与脱敏

- 状态：accepted
- 日期：2026-08-05
- 里程碑：M3
- 命中的 ADR 检查项：4
- 接受：负责人 2026-08-05 裁决「创建 ADR（A/B/C 三份）」并评审接受为 accepted

## 背景

M3 的 `hybrid` 来源策略需要把内部知识与外部 Web 检索融合进同一报告。Research 既要把内部知识摘要用于综合，又不能把私有文档内容外发给 Web 搜索；同时 Knowledge 的权限可能实时变化，Research 持久化内部正文会形成绕过 Knowledge 实时权限的副本。内部知识外发的边界、过滤时机与审计要求是敏感信息处理决策。

该选择决定敏感信息如何进入 Research 内存工作集、哪些内容可进入 Web Query、SSE 与审计中可暴露什么。命中 ADR 检查项 4（数据与安全——敏感信息处理与审计策略）。

## 决策

### minimal_excerpt 仅限 Step 内存（落地 ADR-003）

- Internal Retrieval 返回的 `minimal_excerpt` 只存在于当前 Step 的受控内存工作集；转换为 Evidence 前按 Contract Schema 校验并删除摘录。
- 内部正文不得进入 Task、Step JSON、Agent Event、Trace、错误、SSE、Evidence、Claim、Report 或任何恢复字段。
- 后续阶段确需内部语义输入时，在当前有效租约与权限下重新检索，不从持久数据恢复正文。

### Web Query 域隔离

- Knowledge Query 可保留用户明确提供的内部实体名；Web Query 只能来自原始 Topic、公开 Requirements 与 Planner 产生的公开子问题。
- Internal Retrieval 的 excerpt、内部文档标题、内部命名、检索结果与报告草稿不得自动进入 Web Query。
- Hybrid 两套查询计划在 Planning 输出即显式分离，外发策略校验器检查 Web Query；失败关闭，不降级发送原始私有内容。

### 审计不扩大泄漏面

- 面向用户的研究过程由 `agent_events` 白名单事件投影，不含模型隐藏推理、完整 Prompt 或内部正文。
- 观测与审计字段只记录安全摘要（计数、稳定 ID、策略结果、错误码）；指标标签不得使用 Topic、URL、User UUID、KB UUID 或 Evidence ID 等高基数/敏感值。

## 后果

- 私有文档内容不会自动进入互联网搜索词（M3 退出门禁之一）。
- Research 对内部正文的任何使用都实时受 Knowledge 权限约束，无历史正文副本绕过。
- Web Query 经外发校验器失败关闭，外发边界可审计。

## 被否决方案

### 内部全文直接进入 Synthesis Prompt 并持久化摘要

持久化即形成权限副本，违背 ADR-003。否决。

### 靠人工在 UI 提醒用户不要复制内部内容

无法程序化保证，无法验收。否决。

### Web Query 允许携带检索到的内部标题

内部标题是命名实体，可能泄露文档存在性与命名，且不可控。否决。

## 重新评估触发条件

- 需要允许 Research 缓存内部检索结果超过当前 Step（必须先行定义加密、TTL、清理、禁用失效与审计，并以新 ADR 替代 ADR-003 相应部分）；
- Web Query 外发规则需要扩展；
- 审计指标需要增加敏感标签。

## 与既有 ADR 的关系

- 落地 [ADR-003](ADR-003-internal-evidence-no-content.md) 的语义，不推翻。
- 对齐 [ADR-005](ADR-005-unified-identity-service-auth-egress.md)：Service JWT 与 Internal Retrieval 实时鉴权顺序由 ADR-005 裁决。

## 相关规范

- [Research Pipeline](../../services/research/docs/RESEARCH_PIPELINE.md) §5.3、§8.2、§16
- [身份与访问](../specs/IDENTITY_AND_ACCESS.md)
- [跨服务契约](../../packages/contracts/README.md)
