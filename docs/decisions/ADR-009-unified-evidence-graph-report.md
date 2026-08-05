# ADR-009：统一 Evidence Graph 与报告表达

- 状态：accepted
- 日期：2026-08-05
- 里程碑：M3
- 命中的 ADR 检查项：3、7
- 接受：负责人 2026-08-05 裁决「创建 ADR（A/B/C 三份）」并评审接受为 accepted

## 背景

M3 需要 Research 报告区分内部与外部证据、显式表达共识/冲突/证据不足/时效风险，并把三类来源策略（`knowledge|web|hybrid`）的检索结果统一到同一个证据模型。若内部（Knowledge RetrievalHit）与外部（Web URL）走两套持久化与报告通路，报告无法形成统一引用锚点，冲突披露与完整度计算也无从谈起。

该选择决定 `evidence_items`/`claims`/`evidence_relations`/`report_revisions` 的关系模型、引用闭包与发布原子性，同时影响 Evidence Contract、`docs/specs/API.md` 报告接口、`RESEARCH_PIPELINE.md` 完整度算法与 `DATABASE.md`。因此命中 ADR 检查项 3（公共契约与持久化格式）与 7（跨规范影响）。

## 决策

### 关系化的 EvidenceReference

- `evidence_items` 是 Contract `EvidenceReference` 的关系化持久表示；`source_type=internal|web` 两类字段严格互斥。
- Internal：稳定 KB/Document/Document Version/Segment ID、显示名快照、位置、时间与评分摘要；无任何正文列（对齐 ADR-003）。
- Web：引用 `web_sources`，保存 canonical URL 快照与抓取时间快照；正文只在 Task 内使用，到期清空正文但保留引用结构。
- 唯一键：Internal `(task_id, kb, document, version, segment)`；Web `(task_id, web_source_id)`。`validity=available|restricted|missing|stale` 是观察状态而非授权凭证。

### Claim 与 Relation 表达研究结论

- `claims` 是报告的最小结论单元，`certainty`/`qualification` 由 Pipeline 定义受控枚举或范围值，不复制原文。
- `evidence_relations` 固定 `supports|contradicts|context`，`confidence` 只代表关系判断信心，不代表来源绝对真实性；重复 `(claim, evidence, relation_type)` 合并。
- 存在 `contradicts` 时必须生成冲突披露或限定，不得合成为无条件确定结论；未披露冲突使发布硬门槛失败。

### 程序化完整度与原子发布

- `evidence_completeness` 三分项（question_coverage / channel_success / claim_coverage）与最终分由固定算法计算并持久化到 Revision 摘要，不由 LLM 直接给出，可复算、可审计。
- 发布流程：创建 `building` Revision → 写 Section/Claim/Relation → 校验引用闭包、同 Task/Revision、内部正文禁入、完整度门禁 → 单事务置 `published` 并切换 `reports.current_revision_id`。
- published Revision 不可变；v1.0 只支持整份重生成，失败 Revision 不成为当前版本。

## 后果

- 内部与外部证据统一到同一引用闭包，报告可区分来源类型并保留可追溯的 URL/位置/时间。
- 冲突、证据不足与时效风险在报告局限与 Claim 限定中显式表达，防止合成无条件确定结论。
- 完整度可审计、可复算，为 PRD AC-001 引用率与 AC-010 可追溯性提供可验证入口。

## 被否决方案

### 报告内嵌自由文本，不建 Evidence/Claim 关系模型

无法保证引用闭包、无法程序化计算完整度、无法表达并强制冲突披露。否决。

### Web 与 Internal 各建一套 Evidence 表

统一引用锚点与跨来源比较无法实现，报告结构分裂。否决。

### 由 LLM 直接给出完整度分数

分数不可复算、不可审计，无法作为发布硬门槛。否决。

## 重新评估触发条件

- 报告需要局部章节再生成（当前 v1.0 明确不做）；
- Evidence Contract 或报告 Schema 需要改变；
- 需要跨 Task 引用或跨用户共享 Evidence。

## 与既有 ADR 的关系

- 对齐 [ADR-003](ADR-003-internal-evidence-no-content.md)：Evidence/Claim/Report 均不含内部正文，正文访问实时鉴权。
- 不改变既有 accepted ADR。

## 相关规范

- [Research Pipeline](../../services/research/docs/RESEARCH_PIPELINE.md) §8、§9、§10、§11
- [Research 数据库](../../services/research/docs/DATABASE.md) §6、§7
- [API 与事件协议](../specs/API.md) §9
- [跨服务契约](../../packages/contracts/README.md)
