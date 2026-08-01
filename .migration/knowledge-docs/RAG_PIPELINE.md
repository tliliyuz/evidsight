# EvidSight Knowledge RAG Pipeline 设计

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认设计 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-07-31 |
| 来源基线 | DocMind RAG Pipeline 与已采纳 ADR |

> 本文是 Knowledge 文档入库、检索核心、Chat 编排和 Internal Retrieval Provider 的权威规范。数据持久化见 [DATABASE.md](DATABASE.md)，HTTP/SSE 见 [`docs/specs/API.md`](../../../docs/specs/API.md)，跨服务字段见 [`packages/contracts/`](../../../packages/contracts/README.md)。本文不定义 Research Agent、Evidence Graph 或报告生成。

## 1. 目标与边界

Pipeline 必须同时支持：单 KB 企业知识问答、受限多 KB Internal Retrieval、可恢复版本化入库、稳定来源定位和失败关闭的权限边界。

v1.0 继承 DocMind 已验证的 Query Rewrite、Vector+BM25、RRF、Coarse Rank、Rerank、句级修辞过滤、Evidence Review、Evidence Highlight 和三层审计。继承不等于照搬实现；所有行为以本文及其引用的 EvidSight 权威规范为准。

明确不做：多 KB Chat、互联网搜索、Research 规划与综合、跨任务 Evidence 复用、共享 ORM、暴露 Chroma/Redis/文件路径，以及保存模型隐藏推理。

## 2. 组件与职责

```text
Knowledge Pipeline
├── Ingestion Pipeline
│   └── Validate → Parse → Structure/Chunk → Embed → Index → Verify → Publish
├── Retrieval Core
│   └── Vector/BM25 → Per-KB RRF → Coarse Rank → Cross-KB Merge → Rerank → Locate
├── Chat Orchestrator
│   └── Intent → Rewrite → Single-KB Retrieval → Review → Generate → Audit → SSE
└── Internal Retrieval Provider
    └── Service/Contract/Authz → Bounded Multi-KB Retrieval → RetrievalHit
```

各组件使用内部纯数据 DTO，不跨层传 ORM 对象。Retrieval Core 不判断用户角色、不发送 SSE、不写 Research 数据、不调用答案生成模型。调用方必须在进入 Core 前完成所需授权。

## 3. 文档入库状态机

每次首次入库或重处理创建独立 `document_versions` 记录：

```text
queued → parsing → chunking → embedding → indexing → verifying → ready
   └────────────── 任一阶段不可恢复错误 ──────────────→ failed
```

- API 校验身份、KB WRITE、文件类型/大小和内容哈希，保存文件并提交 Document Version 后才投递 `knowledge.ingest`。
- Worker 使用 Version UUID 作为幂等键；重复投递不得生成重复 Chunk 或向量。
- 每一阶段完成后提交 Checkpoint，再进入下一阶段。
- `queued` 或超时非终态 Version 由启动/周期扫描恢复；Redis/Celery 不是真实状态源。
- 新 Version 在 `ready` 且发布前不可检索；旧 Active Version 继续服务。
- 核心产物完整但页码、表格或章节增强部分失败时可标为 `ready_with_warnings`；不得用该状态容忍缺 Chunk 或缺向量。

对外 Document 状态映射固定为：Version `queued` 对应 `queued`；解析至验证阶段对应 `processing`；`ready` 对应 `completed`；`ready_with_warnings` 对应 `partial`；`failed` 对应 `failed`。内部阶段名不得直接泄漏为不稳定 API 枚举。

## 4. 解析、分块与索引发布

### 4.1 解析与结构化

PDF 使用 PyMuPDF 主解析、pdfplumber 按需提取表格；DOCX、Markdown 和纯文本使用对应确定性解析器。解析输出统一为带页码、章节路径、段落与字符区间的中间结构。解析器不得把临时路径写入业务字段或错误响应。

分块保留 DocMind 的递归分隔策略和重叠语义；精确默认值属于配置 Schema。每个 Segment 获得稳定 UUID，并携带 Document Version、顺序、Token 估算和受控位置。相同 Version 的 `(document_id, chunk_index)` 唯一。

### 4.2 Staging 与原子发布

MySQL Section/Chunk 携带 `document_version_id`。Embedding 先写入受控 staging 产物，不提前写入在线 Chroma Collection。不得依靠 Chroma Version metadata 过滤隔离新旧版本，因为这会重新引入 per-KB Collection 已消除的过滤全扫描。

发布前必须验证：

1. 解析声明的 Segment 数等于 MySQL Chunk 数；
2. 需要 Embedding 的 Segment 数等于成功 Embedding 数；
3. MySQL Segment UUID 集合与 Chroma Version 向量 ID 集合一致；
4. 所有位置可解释且 Document/KB 归属一致；
5. KB 与 Document 未进入 `deleting`。

验证通过后使用 KB 短时发布锁：

1. 将 KB `index_status` 设为 `updating` 并递增 `index_generation`；
2. 新检索对该 KB 有界等待，超时返回可重试不可用错误；
3. 将 staging 向量写入现有 per-KB Collection；
4. 在 MySQL 事务中切换 `documents.active_version`；
5. 删除旧 Version 向量并校验在线集合；
6. 清理 staging 产物，将 KB 恢复为 `ready`。

发布窗口内不得执行该 KB 检索。Worker 崩溃后，恢复器依据 MySQL Active Version：切换前删除新向量并回滚；切换后补齐新向量、删除旧向量并完成发布。只有 Chroma 与 Active Version 一致后才能解除锁。该锁避免 metadata 过滤和全 KB Collection 重建，同时保证外部看不到新旧混合结果。

## 5. 缓存与删除一致性

- BM25 按 KB 建立 L1 进程缓存、L2 Redis Token Cache、L3 MySQL 懒加载；缓存不含 Chunk 原文。
- 文档版本发布、删除完成和 KB 删除必须使对应 KB 的 BM25 缓存失效；TTL 只作兜底。
- BM25 评分后按 Segment ID 从 MySQL 批量读取少量 Active Version 原文。
- 超过 `BM25_MAX_CHUNKS` 的 KB 跳过 BM25 并记录降级；不得因此跳过 Vector。
- KB `deleting` 后立即停止新检索，Worker 幂等清理文件、per-KB Collection 和 MySQL 层级，最后删除 KB。
- Document 删除/重处理只操作其所属 KB Collection 和目标 Version，不扫描其他 KB。

## 6. Retrieval Core

单 KB顺序固定为：Query Embedding → Vector 与 BM25 → RRF → Coarse Rank → Rerank → 句级过滤与定位。

### 6.1 Vector 与 BM25

Vector Store 必须显式接收单个 KB 内部 ID，并只读取 Document Active Version。BM25 只索引可检索 Version；缓存 Key 含 KB 及索引世代，避免发布后读取旧 Token 集。

### 6.2 融合、粗排与精排

- Vector/BM25 在单 KB 内使用 RRF 合并，避免直接比较异构裸分。
- Coarse Rank 使用可用的向量相似度过滤明显噪声；无向量分的 BM25 强命中不能仅因缺分被删除。
- Rerank 对最终候选统一评分；Provider 失败时回退到 RRF/Coarse 顺序。
- 每个分数都带 `score_kind` 与阶段排名，Consumer 不比较不同种类裸值。

### 6.3 Evidence 定位

句级修辞过滤移除只具引用/标题等非陈述作用的句子；Evidence Highlight 使用确定性句级匹配定位最小片段。句级定位失败时允许降级为 Chunk 级片段并标记定位精度，不得编造页码或章节。

## 7. 多 KB Internal Retrieval

执行前必须按顺序验证 Research 服务身份、Contract、用户 active、所有 KB active 及逐 KB READ。任一失败不进入 Core。

受限扇出规则：

1. Vector 最多同时处理 2 个 KB；BM25 同时只处理 1 个 KB。
2. 每个 KB 独立执行 Vector/BM25/RRF，建立有限候选池。
3. 按 KB 内排名公平抽取跨 KB 候选，防止大 KB 垄断。
4. 对跨 KB 候选执行统一 Rerank，按 Segment UUID 去重并截取全局 `limit`。
5. 返回 Contract `RetrievalHit`，只含稳定 UUID、显示信息、位置、最小片段、受控分数与时间。

不允许返回部分 KB 的静默成功。单个 KB 中 Vector/BM25 一路失败可由另一路降级；该 KB 全部通道失败时整次返回 `INTERNAL_RETRIEVAL_UNAVAILABLE`。超大 KB 按策略跳过 BM25不等于 KB失败，但 Vector 必须成功。

Internal Retrieval 不执行 Chat Intent、历史 Rewrite、Prompt、答案生成、SSE 或持久化 EvidenceReference。

`/internal/v1/retrieval/resolve` 只按 Contract 中的 KB/Document/Document Version/Segment 稳定身份精确读取当前仍可访问的最小正文。它复用相同的服务认证、用户启用和逐 KB READ 校验，但不执行向量/BM25、RRF 或 Rerank；不得把已删除 Version 静默解析为当前 Active Version。

## 8. Chat Orchestrator

Chat v1.0 绑定单个 KB。处理顺序：

1. 验证用户 active、Conversation owner、KB active 与当前 READ；
2. 事务写入 User Message 与 Generation `pending`，发送 `meta`；
3. Generation 改为 `running`；执行 Intent；
4. 有明确多轮指代时用最近有限历史 Rewrite，否则保留原问题；
5. Knowledge 意图进入单 KB Retrieval Core；Meta/Casual 路径不得携带私有检索正文；
6. Evidence Review 对实际进入 Prompt 的片段执行门控；无陈述性证据时不调用 LLM；
7. 按相关性和 Token 预算组装最小 Prompt，流式发送 `message.delta`；
8. 对完整答案执行引用存在性、来源一致性和句级回溯审计；
9. 成功时在一个事务写 Assistant Message、`message_sources` 和 Generation `completed`；
10. 发送过滤后的 `sources`，最后发送唯一 `done`。

多轮历史不得扩展 KB 范围。Rewrite 只用于检索，不覆盖用户原问题。Prompt 和回答不得保存模型隐藏推理。

## 9. Chat SSE 与持久化

事件顺序必须符合 API：`meta` → 零到多个 `message.delta` → `sources` → `done`。心跳使用注释帧，不占业务事件 ID。

- Delta 仅发送并保存在受限内存缓冲，不逐 Token 写库。
- 只有生成与最终审计全部成功才写 Assistant Message 和 Sources。
- 断线、显式取消、禁用信号、撤权或失败将 Generation 写入唯一终态，不保存半截 Assistant Message。
- 失败发送安全 `error` 后关闭，禁止发送 `done`。
- User Message 保留；重试产生新 Generation，不覆盖旧终态。
- `sources` 只包含最终回答实际引用且通过过滤的来源；不得发送未引用候选池。

## 10. Evidence Review 与审计

LLM 前 Evidence Review 以过滤后的实际片段判定 `ALLOW|REJECT`。全部无陈述性证据时使用稳定拒答，不产生伪造来源。

LLM 后三层审计至少包含：引用存在性、引用与来源一致性、答案关键陈述的句级回溯。审计失败若会使答案看似有据但实际无据，则失败关闭；仅置信度增强信息缺失时可降级并明确标记。Message Sources 只保存稳定引用和位置，不复制 Chunk 正文。

## 11. 失败、超时与取消

| 故障 | 行为 |
|:---|:---|
| 权限、用户、Contract | 失败关闭，不检索 |
| 单路 Vector/BM25 | 使用另一路并 Trace 降级 |
| 单 KB 全部检索通道 | 请求失败 |
| Rerank Provider | 回退 RRF/Coarse |
| Evidence 句级定位 | 降级 Chunk 位置，标记精度 |
| Evidence Review 无证据 | 稳定拒答，不调用 LLM |
| LLM/最终审计 | SSE error，不保存 Assistant |
| 客户端断线/取消 | 尽快停止 Provider 调用，Generation 终态 |
| Worker 丢失 | 从持久 Version 状态恢复 |

所有外部 Provider 调用设置超时、有限重试和取消传播。重试只用于幂等阶段；不得重复发布 Version 或重复生成已确认 Assistant Message。

## 12. Trace、指标与隐私

Trace 记录阶段耗时、候选数量、KB 数、缓存命中、BM25 跳过、降级、Token/成本、Version 与请求关联，不记录完整 Prompt、凭证、全量候选正文或模型隐藏推理。

最低指标：入库各阶段成功/失败/恢复数、Version 发布耗时、MySQL/Chroma parity 失败、Vector/BM25/Rerank 延迟与降级率、BM25 跳过率、跨 KB 请求规模、Chat TTFT/总延迟/取消率、Evidence Review 拒绝率、引用定位率和 SSE 终态计数。

Internal Query 和最小片段仅用于内部处理，不得自动转发互联网搜索服务。向外部 Embedding/Rerank/LLM 发送内容必须满足身份规范的数据外发策略。

## 13. 测试与质量门禁

- 入库每阶段 RED/GREEN、重复投递、Worker 中断、恢复和取消；
- 新 Version 发布前不可检索，切换后无新旧混合；
- MySQL Chunk、Embedding 与 Chroma ID 集合不一致时禁止发布；
- private KB 越权路径为零，禁用与 deleting 状态失败关闭；
- 单 KB 两路检索、RRF、Rerank、Evidence Review 和全部降级；
- 多 KB 全授权/任一拒绝、并发上限、公平抽取、去重和全局排序；
- Contract 正反 Fixture 在 Provider 侧全部通过；
- Chat SSE 顺序、唯一终态、断线、取消和事务持久化；
- 固定评估集 Recall@5、引用定位率、无证据拒答率和跨 KB 泄漏；
- 2C2G 下峰值内存、P95 检索延迟和大 KB BM25保护。

质量阈值的数值和评估集版本由 `docs/specs/TESTING.md` 统一发布；没有实际运行证据不得声称达到发布门禁。

## 14. 验收场景

1. 新文档只有 parity 验证和原子发布后才可检索。
2. 重处理期间旧 Version 服务，切换后不返回混合版本。
3. 单 KB Chat 保持 DocMind 核心召回质量并返回可定位来源。
4. 多 KB请求受限扇出、公平合并且不暴露实现字段。
5. 任一 KB 无权时整次 Internal Retrieval 在检索前拒绝。
6. 某 KB 全通道失败时不返回不完整成功。
7. Chat 断线、取消、LLM 或审计失败均无半截 Assistant Message 和 `done`。
8. Evidence不足时跳过 LLM并稳定拒答。
9. KB删除与版本发布使 BM25缓存及时失效。
10. Worker消息丢失后可从 MySQL持久状态恢复。

## 15. 后续边界

任何改变 per-KB Collection、跨 KB融合、Evidence门控、正文外发、发布原子性或失败关闭语义的实现必须先修订本文；涉及服务职责、安全或数据生命周期变化时新增 ADR。Research Pipeline 只能消费 Internal Retrieval Contract，不得导入本 Pipeline 内部 DTO。
