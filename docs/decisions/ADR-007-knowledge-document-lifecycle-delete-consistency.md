# ADR-007：Knowledge 文档版本化生命周期与删除一致性

- 状态：accepted
- 日期：2026-08-04
- 里程碑：M2
- 命中的 ADR 检查项：4、5

## 背景

M2 需要稳定文档入库、重处理与删除链路，并让 Internal Retrieval 与 Evidence 在文档被重处理或删除后仍保持一致、可追溯和可恢复。Knowledge 的写入横跨 MySQL、对象存储与 Chroma，三者无法组成单事务；若任一步骤崩溃，检索可能暴露新旧混杂结果、半删状态，或残留无法清理的 staging 产物。

该选择决定 Knowledge 数据生命周期、检索一致性与删除可恢复性的长期机制，影响数据库 Schema、入库状态机、文档 API 状态枚举，以及 Internal Evidence 的有效性语义（`missing|stale`）。因此命中 ADR 检查项 4（数据与安全）与 5（核心机制）。

## 决策

### 版本化生命周期

- 每次首次入库或重处理创建独立 `document_versions` 记录，以 Version UUID 作为 Worker 幂等键；重复投递不得生成重复 Chunk 或向量。
- 版本状态机固定为 `queued → parsing → chunking → embedding → indexing → verifying → ready`；任一阶段不可恢复错误进入 `failed`。核心产物完整但页码、表格或章节增强部分失败时可标为 `ready_with_warnings`，不得用该状态容忍缺 Chunk 或缺向量。
- 每一阶段完成后提交 Checkpoint（`last_success_batch`）再进入下一阶段；MySQL 的 Document/Chunk/Version 状态是生命周期唯一权威，Chroma 与 Redis/Celery 均不作为权威。
- 对外 Document 状态映射固定为：`queued`→`queued`、解析至验证→`processing`、`ready`→`completed`、`ready_with_warnings`→`partial`、`failed`→`failed`；内部阶段名不得泄漏为不稳定 API 枚举。
- 新 Version 在 `ready` 且发布前不可检索；旧 Active Version 继续服务。Internal Evidence Resolve 只按 Contract 中的稳定身份精确读取当前仍可访问的正文，不静默切换新 Active Version。

### Staging 与原子发布

- MySQL Section/Chunk 携带 `document_version_id`；Embedding 先写入受控 staging 产物，不提前写入在线 Chroma Collection。不得依靠 Chroma metadata 过滤隔离新旧版本。
- 发布前必须验证：解析声明 Segment 数等于 MySQL Chunk 数、需 Embedding 的 Segment 数等于成功 Embedding 数、MySQL Segment UUID 集合与 Chroma Version 向量 ID 集合一致、所有位置可解释且 Document/KB 归属一致、KB 与 Document 未进入 `deleting`。
- 发布使用 KB 短时发布锁：置 `index_status=updating` 并递增 `index_generation`；新检索对该 KB 有界等待，超时返回可重试不可用错误；写入 staging 向量 → 在 MySQL 事务中切换 `documents.active_version` → 删除旧 Version 向量并校验在线集合 → 清理 staging 产物 → 恢复 `ready`。
- 发布窗口内不得执行该 KB 检索。Worker 崩溃后恢复器依据 MySQL Active Version：切换前删除新向量并回滚，切换后补齐新向量、删除旧向量并完成发布；只有 Chroma 与 Active Version 一致后才能解除锁。

### 删除一致性

- 每 KB 映射独立 Chroma Collection，名称由 Knowledge 内部根据 KB 内部 ID 生成，不属于外部契约。BM25 缓存按 KB 隔离且不含 Chunk 原文。
- 文档版本发布、删除完成和 KB 删除必须使对应 KB 的 BM25 缓存失效；TTL 只作兜底。
- KB 删除顺序：事务内标记 `deleting` 并写入审计提交 → API、Chat 与 Internal Retrieval 立即拒绝该 KB 的新操作 → Worker 幂等清理上传对象与 per-KB Collection → 删除 MySQL Document/Section/Chunk → 最后物理删除 KB 行。任一步失败保持可恢复状态。
- Document 删除/重处理只操作其所属 KB Collection 和目标 Version，不扫描其他 KB。
- 启动与周期扫描重新投递长期停留在非终态的 KB 和 Document；Redis/Celery 不是任务唯一事实源。

### 检索与授权封装

- Internal Retrieval 对每次请求按固定顺序重新校验服务身份、Contract、用户启用与全部目标 KB 当前 READ 权限，再进入检索 Core；任一步失败不执行后续步骤。授权语义对齐 ADR-002/005，本 ADR 不重复定义。
- 对 Research 不暴露 MySQL、Chroma Collection 名称、缓存 Key、文件路径或内部阶段名。

## 后果

- 文档入库、重处理、删除在任意阶段崩溃后均可从持久状态恢复，不产生新旧混杂或半删可见状态。
- 发布窗口内目标 KB 短暂不可检索，换取一致性；对 2C2G 试点基线，per-KB 锁与幂等清理是可接受的成本。
- Evidence 在文档重处理或删除后可能变为 `missing|stale`，历史引用保留元数据但不授予旧版本正文访问权（对齐 ADR-003）。

## 被否决方案

### 原地增量更新（无版本切换）

直接在在线 Collection 上修改/删除，无版本切换。重处理失败无法回滚；检索可能看到新旧混合；删除中途崩溃没有恢复点。否决。

### 每次发布全量重建 per-KB Collection

发布窗口长、期间 KB 不可检索；2C2G 基线无法支撑频繁重处理与删除。否决。

### 依靠 Chroma Version metadata 过滤隔离新旧版本

重新引入 per-KB Collection 已消除的过滤全扫描，无法保证一致性与 2C2G 检索时延。否决。

## 重新评估触发条件

- 引入独立存储后端或分布式事务能力，使 MySQL、对象存储与向量库可组成单事务；
- 2C2G 基线变化或检索延迟指标无法满足时，重新评估 per-KB 锁窗口与有界等待；
- 需要改变对外文档状态枚举、Active Version 切换语义或 Evidence 有效性语义。

## 与既有 ADR 的关系

- 对齐 [ADR-002](ADR-002-service-boundary.md)：Knowledge 拥有数据与生命周期；Research 只经 Contract 消费。
- 对齐 [ADR-003](ADR-003-internal-evidence-no-content.md)：删除/重处理后 Evidence 只保留稳定身份与位置元数据，正文访问实时鉴权。
- 对齐 [ADR-005](ADR-005-unified-identity-service-auth-egress.md)：Internal Retrieval 的实时授权顺序与失败关闭由 ADR-005 裁决；M2 的检索权限要求由 ADR-002/005 交叉引用覆盖，不重复定义。
- 不替代现有 accepted ADR。

## 相关规范

- [Knowledge RAG Pipeline](../../services/knowledge/docs/RAG_PIPELINE.md)
- [Knowledge 数据库](../../services/knowledge/docs/DATABASE.md)
- [API 与事件协议](../specs/API.md)
- [跨服务契约](../../packages/contracts/README.md)
- [身份与访问](../specs/IDENTITY_AND_ACCESS.md)
