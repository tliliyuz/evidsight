# EvidSight Knowledge Service 数据库设计

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认设计 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-07-31 |
| 来源基线 | DocMind `backend/docs/DATABASE.md` 与既有 Alembic 历史 |

> 本文是 `platform_db` 与 `knowledge_db` 的表、索引、外键、生命周期和迁移边界的权威规范。身份语义见 [`docs/IDENTITY_AND_ACCESS.md`](../../../docs/IDENTITY_AND_ACCESS.md)，系统数据所有权见 [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md)，跨服务字段见 [`packages/contracts/`](../../../packages/contracts/README.md)。本文不定义 HTTP 字段、RAG 算法或 Research 数据表。

## 1. 目标与边界

Knowledge Service 拥有两个相互隔离的 MySQL 逻辑数据库：

| 数据库 | 所有者模块 | 权威数据 |
|:---|:---|:---|
| `platform_db` | Knowledge 身份模块 | 用户、Refresh Token 会话族、身份审计 |
| `knowledge_db` | Knowledge 业务模块 | KB、文档、章节、分块、会话、消息、引用、生成、Trace 与业务审计 |

两库使用独立账号、最小权限、独立 Alembic version table 和迁移链。不得建立跨数据库外键。Research Service 不得直读任一数据库，只能通过 JWT、公开 API 与 Internal Retrieval Contract 交互。

本设计以 DocMind 现有 Schema 为演进基线：保留成熟的内部 BIGINT 主键、知识层级、会话模型和迁移历史；新增统一 Platform User UUID、稳定 Segment UUID、结构化引用与生成生命周期。两个旧项目没有需迁移的生产用户，因此不设计账号自动合并、旧用户映射或身份双写。

## 2. 通用约定

- 数据库字符集使用 `utf8mb4`；表使用 InnoDB。
- 所有业务时间以 UTC 写入；应用边界序列化为 RFC 3339 UTC。
- `platform_db.users.id` 使用 UUID；Knowledge 业务实体保留 BIGINT 内部主键，并使用唯一 UUID 对外及跨服务引用。
- UUID 由应用生成，视为不透明标识；客户端不得依赖其排序。
- 金额和评分使用定点数，不使用二进制浮点保存权威值。
- JSON 列必须由应用 Schema 校验；不得用任意 JSON 取代稳定、可索引的核心字段。
- 跨库用户引用统一命名为 `platform_user_id` 或 `owner_platform_user_id`，类型与 Platform User UUID 一致，但不建外键。
- 业务错误只保存安全摘要；凭证、完整 Prompt、模型隐藏推理和无关私有正文不得写入日志、Trace 或审计详情。
- 计数缓存和执行进度不是独立事实源；必须能由权威关系或状态记录重新计算。

## 3. 主键与跨服务标识策略

Knowledge 业务表继续使用 BIGINT 聚簇主键，以保留 DocMind 的内部外键、索引和迁移稳定性。以下标识必须使用 UUID：

| 对象 | 内部主键 | 稳定 UUID | 跨服务可见性 |
|:---|:---|:---|:---|
| Platform User | UUID | 同主键 | JWT `sub` 和用户上下文 |
| Knowledge Base | BIGINT | `uuid` | API、Internal Retrieval |
| Document | BIGINT | `uuid` | API、Evidence 来源 |
| Segment/Chunk | BIGINT | `segment_uuid` | Evidence 定位 |
| Conversation | BIGINT | `uuid` | API |
| Message | BIGINT | `uuid` | API、引用关联 |
| Chat Generation | BIGINT | `uuid` | 取消、幂等、Trace |

`chroma_id`、数据库主键、文件存储键和缓存键只在 Knowledge 内部使用，禁止进入 Contract 或外部 API。

## 4. `platform_db`

### 4.1 `users`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | CHAR(36) | PK，Platform User UUID |
| `username` | VARCHAR(64) | UNIQUE，规范化后非空 |
| `password_hash` | VARCHAR(255) | 只存密码哈希，不存算法外的秘密 |
| `role` | ENUM | `user`、`admin` |
| `status` | ENUM | `active`、`disabled` |
| `status_version` | BIGINT | 非负，状态变化递增，用于缓存失效 |
| `disabled_at` | DATETIME | 可空 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

用户名用于 v1.0 登录；Platform User UUID 才是跨服务稳定身份。禁用不删除用户，也不级联删除业务数据。

### 4.2 `refresh_token_families`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | CHAR(36) | PK，Token Family UUID |
| `user_id` | CHAR(36) | FK → `users.id`，CASCADE |
| `created_at` | DATETIME | 初次登录时间 |
| `last_rotated_at` | DATETIME | 最近成功轮换时间 |
| `expires_at` | DATETIME | Family 绝对过期时间 |
| `revoked_at` | DATETIME | 可空；退出、禁用或重放检测时写入 |
| `revoke_reason` | VARCHAR(64) | 受控枚举字符串，可空 |

Family 是退出和重放响应的最小撤销单元。用户禁用时撤销该用户所有未撤销 Family。

### 4.3 `refresh_tokens`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `family_id` | CHAR(36) | FK → `refresh_token_families.id`，CASCADE |
| `token_hash` | VARCHAR(255) | UNIQUE，只保存密码学哈希 |
| `issued_at` | DATETIME | UTC |
| `expires_at` | DATETIME | UTC |
| `rotated_at` | DATETIME | 可空；成功换出新 Token 时写入 |
| `replaced_by_id` | BIGINT | 自引用，可空 |
| `revoked_at` | DATETIME | 可空 |

刷新在单事务中锁定当前 Token、验证 Family 与用户状态、写入替代 Token，并标记旧 Token 已轮换。已轮换 Token 再次出现时撤销整个 Family。

### 4.4 `identity_audit_events`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `event_uuid` | CHAR(36) | UNIQUE |
| `user_id` | CHAR(36) | 可空，不跨删除级联 |
| `actor_user_id` | CHAR(36) | 可空，管理员操作主体 |
| `event_type` | VARCHAR(64) | 登录、刷新、重放、退出、禁用、启用等受控类型 |
| `request_id` | VARCHAR(64) | 请求关联 ID，可空 |
| `outcome` | ENUM | `success`、`denied`、`error` |
| `details` | JSON | 仅允许安全摘要 |
| `created_at` | DATETIME | UTC |

## 5. `knowledge_db` 核心内容表

### 5.1 `knowledge_bases`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK，内部使用 |
| `uuid` | CHAR(36) | UNIQUE，对外标识 |
| `owner_platform_user_id` | CHAR(36) | 创建者 Platform User UUID，无跨库 FK |
| `name` | VARCHAR(128) | 同一 owner 下唯一 |
| `description` | TEXT | 可空 |
| `visibility` | ENUM | `private`、`public` |
| `status` | ENUM | `active`、`deleting` |
| `index_status` | ENUM | `ready`、`updating`、`recovering` |
| `index_generation` | BIGINT | 非负，向量发布世代 |
| `document_count_cache` | INT | 非负缓存，不作为 API 权威计数 |
| `segment_count_cache` | INT | 非负缓存，不作为 API 权威计数 |
| `version` | BIGINT | 乐观并发版本 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

`deleting` 状态立即拒绝新上传、Chat 和 Internal Retrieval。公开可读不等于公开可写；写权限仍由 owner 或管理员治理规则决定。

### 5.2 `documents`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `uuid` | CHAR(36) | UNIQUE，对外与 Evidence 标识 |
| `kb_id` | BIGINT | FK → `knowledge_bases.id`，CASCADE |
| `filename` | VARCHAR(256) | 同一 KB 下唯一 |
| `display_name` | VARCHAR(256) | 用户可见名称 |
| `file_type` | VARCHAR(32) | 允许列表 |
| `storage_key` | VARCHAR(512) | Knowledge 内部存储键，不对外暴露 |
| `file_size` | BIGINT | 非负字节数 |
| `content_hash` | CHAR(64) | 文件内容 SHA-256，用于校验和幂等 |
| `status` | ENUM | `pending`、`processing`、`ready`、`ready_with_warnings`、`failed`、`deleting` |
| `active_version` | INT | 当前可检索版本号，可空 |
| `error_code` | VARCHAR(64) | 安全错误码，可空 |
| `error_summary` | VARCHAR(500) | 安全摘要，可空 |
| `segment_count_cache` | INT | 非负缓存 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

只有 `ready` 与 `ready_with_warnings` 文档的 Active Version 可检索；后者只允许非核心位置/结构增强缺失，不允许 Chunk 或向量不完整。原始文件路径从 DocMind 的 `file_path` 迁移为存储后端无关的 `storage_key`。

### 5.3 `document_versions`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `uuid` | CHAR(36) | UNIQUE，Worker 幂等键 |
| `document_id` | BIGINT | FK → `documents.id`，CASCADE |
| `version` | INT | 同一 Document 内递增且唯一 |
| `status` | ENUM | `queued`、`parsing`、`chunking`、`embedding`、`indexing`、`verifying`、`ready`、`ready_with_warnings`、`failed` |
| `last_success_batch` | INT | 非负 Checkpoint，可空 |
| `expected_segment_count` | INT | 非负，可空 |
| `embedded_segment_count` | INT | 非负，可空 |
| `indexed_segment_count` | INT | 非负，可空 |
| `staging_artifact_key` | VARCHAR(512) | Embedding staging 内部存储键，可空且不对外暴露 |
| `warning_summary` | JSON | 受控非核心警告，可空 |
| `error_code` | VARCHAR(64) | 安全错误码，可空 |
| `error_summary` | VARCHAR(500) | 安全摘要，可空 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |
| `published_at` | DATETIME | 可空 |

`(document_id, version)` 唯一。非 Active Version 不参与检索；Worker 丢失后以 Version 与 KB Index 状态恢复。Staging 产物在发布或回滚完成后必须清理。

### 5.4 `sections`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `document_id` | BIGINT | FK → `documents.id`，CASCADE |
| `document_version_id` | BIGINT | FK → `document_versions.id`，CASCADE |
| `kb_id` | BIGINT | FK → `knowledge_bases.id`，CASCADE，冗余用于受控查询 |
| `title` | VARCHAR(512) | 章节标题 |
| `path` | VARCHAR(1024) | 层级路径 |
| `level` | INT | 1—6 |
| `start_chunk_index` | INT | 非负 |
| `end_chunk_index` | INT | 不小于起始值 |
| `created_at` | DATETIME | UTC |

### 5.5 `chunks`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `segment_uuid` | CHAR(36) | UNIQUE，Evidence 稳定 Segment ID |
| `document_id` | BIGINT | FK → `documents.id`，CASCADE |
| `document_version_id` | BIGINT | FK → `document_versions.id`，CASCADE |
| `kb_id` | BIGINT | FK → `knowledge_bases.id`，CASCADE |
| `section_id` | BIGINT | FK → `sections.id`，SET NULL，可空 |
| `chroma_id` | VARCHAR(256) | Knowledge 内部向量 ID |
| `content` | TEXT | 权威分块正文，仅 Knowledge 内部读取 |
| `chunk_index` | INT | 文档内从 0 开始的稳定顺序 |
| `token_count` | INT | 非负估算值 |
| `location` | JSON | 页码、段落、字符区间等受控定位 |
| `created_at` | DATETIME | UTC |

`(document_version_id, chunk_index)` 唯一。Internal Retrieval 只读取 Document Active Version，并以 `segment_uuid` 返回位置，绝不返回 `id`、`chroma_id` 或存储信息。

## 6. 会话、消息与引用

### 6.1 `conversations`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `uuid` | CHAR(36) | UNIQUE，对外标识 |
| `owner_platform_user_id` | CHAR(36) | 无跨库 FK |
| `kb_id` | BIGINT | FK → `knowledge_bases.id`，SET NULL；v1.0 单 KB 会话 |
| `original_kb_uuid` | CHAR(36) | KB 删除前快照，可空 |
| `original_kb_name` | VARCHAR(128) | KB 删除前快照，可空 |
| `title` | VARCHAR(256) | 会话标题 |
| `message_count_cache` | INT | 非负缓存 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |
| `last_message_at` | DATETIME | 最近一次成功持久化消息时间 |

Chat v1.0 不建立 Conversation—KB 多对多。多 KB Research 通过 Internal Retrieval 实现，其选择范围归 `research_db` 所有。

### 6.2 `messages`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `uuid` | CHAR(36) | UNIQUE |
| `conversation_id` | BIGINT | FK → `conversations.id`，CASCADE |
| `generation_id` | BIGINT | FK → `chat_generations.id`，SET NULL，可空 |
| `role` | ENUM | `user`、`assistant`、`system` |
| `content` | MEDIUMTEXT | 用户可见消息正文 |
| `token_count` | INT | 非负估算值，可空 |
| `feedback` | ENUM | `like`、`dislike`，可空 |
| `created_at` | DATETIME | UTC |

目标 Schema 不保留 `thinking_content`。模型隐藏推理不得进入消息、Trace 或审计记录。

### 6.3 `chat_generations`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `uuid` | CHAR(36) | UNIQUE，取消端点标识 |
| `conversation_id` | BIGINT | FK → `conversations.id`，CASCADE |
| `platform_user_id` | CHAR(36) | 发起用户快照 |
| `kb_uuid` | CHAR(36) | 本次实际使用的单 KB 快照 |
| `idempotency_key_hash` | CHAR(64) | 同用户同端点唯一，可空 |
| `status` | ENUM | `pending`、`running`、`completed`、`failed`、`canceled` |
| `error_code` | VARCHAR(64) | 可空 |
| `error_summary` | VARCHAR(500) | 可空 |
| `input_tokens` | INT | 非负，可空 |
| `output_tokens` | INT | 非负，可空 |
| `started_at` | DATETIME | 可空 |
| `completed_at` | DATETIME | 可空 |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

该表是生成生命周期的事实源。关联消息通过 `messages.generation_id` 查询，避免 Generation 与 Message 形成循环外键。SSE 断开或显式取消只能产生一个终态；失败或取消不得伪造成功 Assistant Message。

### 6.4 `message_sources`

| 字段 | 类型 | 约束与语义 |
|:---|:---|:---|
| `id` | BIGINT | PK |
| `message_id` | BIGINT | FK → `messages.id`，CASCADE |
| `citation_index` | INT | 同一消息内从 1 开始，唯一 |
| `kb_uuid` | CHAR(36) | 来源 KB 稳定 ID |
| `document_uuid` | CHAR(36) | 来源 Document 稳定 ID |
| `segment_uuid` | CHAR(36) | 来源 Segment 稳定 ID |
| `document_display_name` | VARCHAR(256) | 生成时快照 |
| `location` | JSON | 生成时位置快照 |
| `score_summary` | JSON | 受控评分摘要 |
| `validity_at_generation` | ENUM | `available`、`restricted`、`missing`、`stale` |
| `created_at` | DATETIME | UTC |

该表不对 KB、Document 或 Chunk 建强外键，避免来源删除时抹除历史引用；也不得保存 Chunk 正文。用户展开来源时必须以稳定 UUID 向 Knowledge 实时查询和鉴权。

## 7. Trace 与审计

### 7.1 `knowledge_traces`

继承 DocMind Trace 的阶段计时、意图、重写、检索、Rerank、生成和 Evidence Review 摘要，但使用以下稳定顶层字段：`trace_uuid`、`request_id`、`platform_user_id`、Conversation/Generation/KB UUID、状态、响应模式、耗时、Token/成本和 UTC 时间。

阶段详情可使用受 Schema 约束的 JSON。不得保存完整 Prompt、模型隐藏推理、凭证、未命中的 Chunk 正文或完整私有文档；用户问题和命中摘要按部署保留策略最小化、脱敏和清理。

### 7.2 `knowledge_audit_events`

记录 KB 创建/治理/删除、文档上传/重处理/删除、Internal Retrieval 拒绝、内部来源二次鉴权和管理员治理。字段包含事件 UUID、Actor Platform User UUID、目标类型与稳定 UUID、请求 ID、结果、安全详情和 UTC 时间。

Trace 用于性能与质量诊断，Audit 用于安全和治理；两者不得互相替代。

## 8. Per-KB Collection 与关系库一致性

每个 KB 映射到独立 Chroma Collection。Collection 名称由 Knowledge 内部根据 KB 内部 ID 生成，不属于外部契约。

- `vector_store.search/add/delete` 必须显式接收单个 KB 内部 ID。
- `index_status != ready` 时该 KB 不接受新检索；调用方有界等待后使用可重试不可用错误。
- KB 删除可 drop 整个 Collection；Document 删除只在所属 Collection 内按内部文档标识删除。
- MySQL 的 Document/Chunk 状态是生命周期权威；Chroma 不作为文档存在性、权限或计数的权威来源。
- BM25 索引和缓存按 KB 隔离，缓存不保存 Chunk 原文，命中后从 MySQL 批量读取最小正文。
- 多 KB Internal Retrieval 必须逐 KB 鉴权和检索，再执行跨 KB 归一化、去重与全局排序；不得构造共享 Collection 绕过隔离。
- 2C2G 基线下，多 KB BM25 必须有并发和内存上限；精确调度与融合算法由 RAG Pipeline 规范定义。

## 9. 生命周期与一致性

### 9.1 KB 删除

1. 事务内将 KB 标记为 `deleting`，写入审计并提交。
2. API、Chat 和 Internal Retrieval 立即拒绝该 KB 的新操作。
3. Worker 幂等清理上传对象与 per-KB Collection。
4. 删除 MySQL Document/Section/Chunk；Conversation 在删除前保存 KB UUID/名称并解除 `kb_id`。
5. 最后物理删除 KB 行。

任一步失败都保持可恢复状态。Redis/Celery 不是任务唯一事实源；启动与周期扫描必须重新投递长期停留在非终态的 KB 和 Document。

### 9.2 Document 入库、重处理与删除

Document Version 状态与 `last_success_batch` 共同表示恢复点。数据库写入、文件存储和向量写入无法组成单事务，因此每一步必须幂等，并在下一步前验证上一阶段产物。Embedding 先进入 staging；发布使用 KB `index_status` 短时阻断检索，切换 Active Version 并清理旧向量后才恢复 `ready`，不得返回新旧混杂结果。

### 9.3 用户禁用与来源访问

禁用用户不触发业务数据级联删除。关键写入、Chat、Internal Retrieval 和来源展开查询当前 Platform 状态；状态缓存依据 `status_version` 失效。历史引用的生成时状态只用于解释，不能替代当前授权。

## 10. 索引与约束

除主键和外键索引外，最低索引如下：

| 表 | 索引 | 用途 |
|:---|:---|:---|
| `users` | UNIQUE `username` | 登录 |
| `refresh_tokens` | UNIQUE `token_hash` | 刷新与重放检测 |
| `refresh_token_families` | `(user_id, revoked_at, expires_at)` | 用户会话撤销 |
| `identity_audit_events` | `(user_id, created_at)`、`request_id` | 身份审计 |
| `knowledge_bases` | UNIQUE `uuid`、UNIQUE `(owner_platform_user_id, name)`、`(owner_platform_user_id, status, updated_at)`、`(index_status, updated_at)` | 资源定位、列表与索引恢复扫描 |
| `documents` | UNIQUE `uuid`、UNIQUE `(kb_id, filename)`、`(kb_id, status)` | 文档列表与检索资格 |
| `document_versions` | UNIQUE `uuid`、UNIQUE `(document_id, version)`、`(status, updated_at)` | 原子发布与恢复扫描 |
| `sections` | `(document_version_id, start_chunk_index)` | 来源定位 |
| `chunks` | UNIQUE `segment_uuid`、UNIQUE `(document_version_id, chunk_index)`、`kb_id` | Evidence 与批量原文读取 |
| `conversations` | UNIQUE `uuid`、`(owner_platform_user_id, last_message_at)` | 会话列表 |
| `messages` | UNIQUE `uuid`、`(conversation_id, created_at)`、`generation_id` | 消息历史与生成关联 |
| `chat_generations` | UNIQUE `uuid`、`(status, updated_at)`、`(conversation_id, created_at)` | 取消、历史和恢复扫描 |
| `message_sources` | UNIQUE `(message_id, citation_index)`、`segment_uuid` | 引用联动 |
| Trace/Audit | `request_id`、时间与受控分类复合索引 | 诊断、清理和治理 |

所有 Check 约束同时由应用 Schema 验证。删除、恢复和权限查询必须使用索引支持的条件，禁止先读取全量再在应用层过滤。

## 11. 迁移策略

目标迁移遵循 expand/contract，且不修改 DocMind 已发布 Alembic revision：

1. 原样导入 DocMind Alembic 历史并确认唯一 head。
2. 为 `platform_db` 建立独立 Alembic 配置、version table 和首个统一身份 revision。
3. 在 Knowledge 表扩展 Platform User UUID、Document Version、Segment UUID、Message UUID、Generation、结构化引用和审计结构。
4. 初始化统一用户；需保留的非用户演示数据明确重新归属到该用户 UUID。
5. 分批回填 UUID 与存储键，校验非空、唯一性和引用数量。
6. 应用切换到 Platform UUID 和新引用结构，完成新旧字段双读对比。
7. 在 Consumer 全部切换后删除 Knowledge 旧 `users`、`refresh_tokens`、BIGINT 用户外键、`thinking_content` 和失效 JSON 引用。
8. 建立或验证新索引、约束和外键，执行 MySQL/文件/Chroma 抽样一致性检查。

具体停机窗口、批次大小、校验 SQL、备份、前滚修复和回滚点由 `docs/DATA_MIGRATION_AND_ROLLBACK.md` 定义。不可逆内容删除在可验证备份前不得执行。

## 12. 备份、恢复与保留

- `platform_db`、`knowledge_db`、uploads 和 Chroma 使用同一备份批次标识。
- 备份记录数据库 revision、对象数量、Collection 清单、校验和和镜像版本。
- Redis 不作为业务恢复源。
- 恢复后校验用户状态、KB/Document/Chunk 数量、文件存在性、向量抽样、会话消息、引用定位和审计连续性。
- Trace、Audit、失败摘要和上传文件分别配置保留策略；清理任务必须可审计且不得破坏法定或业务保留要求。

## 13. 验收场景

1. 两个逻辑数据库使用独立账号和 Alembic revision，Research 账号无法直读。
2. KB、Document、Segment、Conversation、Message 和 Generation 的稳定 UUID 唯一且不暴露内部主键。
3. 私有 KB 越权、禁用用户和 `deleting` KB 在读取正文或检索前被拒绝。
4. per-KB Collection 不发生跨 KB 命中；删除单个 KB 不扫描或删除其他 Collection。
5. Worker 消息丢失后，非终态 KB、Document 和 Generation 可由持久状态恢复。
6. Internal Retrieval 返回 Segment UUID 和最小片段，但 Research 可持久化引用不含正文。
7. KB 删除后 Conversation、Message 和引用仍可解释，原文访问返回明确不可用状态。
8. Chat v1.0 始终绑定单个 KB；多 KB Research 不创建 Conversation—KB 关联。
9. 用户禁用后历史数据保留，但不能新建 Chat、执行 Internal Retrieval 或展开内部来源。
10. 备份恢复后 MySQL、uploads 与 Chroma 的批次、数量和抽样内容一致。
11. 迁移后不存在旧用户身份双写、`thinking_content` 或跨数据库外键。
12. 所有目标查询命中预期索引，删除、权限和列表查询不依赖应用层全量过滤。

## 14. 后续依赖

Knowledge RAG Pipeline 已据此定义单 KB Chat、受限多 KB Internal Retrieval、入库/重处理 Checkpoint、跨 KB 融合、Evidence 定位、Generation 持久化时点和失败恢复。[`Research Database`](../../research/docs/DATABASE.md) 只保存 Contract 允许的 Knowledge 稳定引用，不得复制 Chunk 正文或 Knowledge 内部存储标识。
