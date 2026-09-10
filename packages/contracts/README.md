# EvidSight 跨服务契约设计

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认设计 |
| 文档版本 | v1.0 |
| Contract 设计基线 | `1.0.0-draft`（Schema/Fixture 落地并通过双方测试后发布 `1.0.0`） |
| 最后更新 | 2026-08-09 |

> 本文是 `packages/contracts/` 的权威设计入口。HTTP 路由、认证载体和状态码由 [`docs/specs/API.md`](../../docs/specs/API.md) 定义，身份与实时授权由 [`docs/specs/IDENTITY_AND_ACCESS.md`](../../docs/specs/IDENTITY_AND_ACCESS.md) 定义，服务边界由 [`docs/specs/ARCHITECTURE.md`](../../docs/specs/ARCHITECTURE.md) 定义。本文只定义跨服务纯数据 Schema、版本规则与契约测试。

M1 的服务身份、用户授权上下文和失败关闭策略由已接受的 [`ADR-005`](../../docs/decisions/ADR-005-unified-identity-service-auth-egress.md) 裁决。现在可以整理 Contract Schema/Fixture 并编写 Provider/Consumer 验收测试；发布 `1.0.0` 或编写生产实现仍须先观察对应验收测试的正确 RED。

## 1. 目标与边界

本包使 Knowledge Service 与 Research Service 可以独立实现和部署，并通过可执行契约验证双方对 Internal Retrieval 和 Evidence 的理解一致。

v1.0 只包含：

- Internal Identity Status Response；
- Internal Retrieval Request/Response；
- Internal Evidence Resolve Request/Response；
- 仅供当前研究步骤使用的 `RetrievalHit`；
- 可持久化和进入报告的 `EvidenceReference`；
- Evidence 与结论之间的 `EvidenceRelation`；
- 跨服务错误信封、版本信封和固定 Fixture；
- 从 JSON Schema 生成或校验的 Python/Pydantic 与 TypeScript 类型。

本包不包含：

- 外部 REST API DTO、Chat SSE 或 Research SSE 业务事件；
- JWT、服务凭证、HTTP 路由、中间件或授权实现；
- Task/Phase/Step、检索算法、排序策略或报告渲染状态机；
- SQLAlchemy Model、数据库表、Chroma Collection、磁盘路径、缓存 Key 或服务内部对象；
- 任一服务的业务代码或对任一 `app` 包的导入。

## 2. 权威源与生成物

JSON Schema 是字段、类型、约束和版本的唯一权威源。Pydantic 与 TypeScript 类型均为可重建生成物，不得手工新增或修改业务字段。

建议目录：

```text
packages/contracts/
├── README.md
├── schemas/
│   └── v1/
│       ├── common.schema.json
│       ├── identity-status-response.schema.json
│       ├── retrieval-request.schema.json
│       ├── retrieval-response.schema.json
│       ├── retrieval-hit.schema.json
│       ├── evidence-resolve-request.schema.json
│       ├── evidence-resolve-response.schema.json
│       ├── evidence-reference.schema.json
│       ├── evidence-relation.schema.json
│       └── error-response.schema.json
├── fixtures/
│   └── v1/
│       ├── valid/
│       └── invalid/
└── generated/
    ├── python/
    └── typescript/
```

所有 Schema 使用 JSON Schema 2020-12、稳定 `$id` 和相对 `$ref`。生成物必须带“由 Schema 生成，请勿手工编辑”标记；CI 重新生成后工作区必须无差异。

## 3. 参与方与数据流

| 数据方向 | Provider | Consumer | 责任 |
|:---|:---|:---|:---|
| Identity Status Response | Knowledge | Research | Knowledge 返回最小权威状态；Research 在创建长期任务前失败关闭 |
| Retrieval Request | Research | Knowledge | Research 生成合法请求；Knowledge 严格校验结构，不信任请求中的授权结论 |
| Retrieval Response | Knowledge | Research | Knowledge 完成实时授权和检索；Research 只消费契约字段 |
| Evidence Reference | Research | Research API/Web | Research 将临时命中转换为无内部正文的持久引用 |

处理顺序固定为：

```text
验证 Research 服务身份
  → 验证 Contract 版本与请求结构
  → 验证用户存在且启用
  → 逐个验证 KB 当前 READ 权限
  → 执行检索
  → 返回最小 RetrievalHit
  → Research 转换为 EvidenceReference
  → 持久化 Evidence/关系并生成报告
```

任一步失败不得执行后续步骤。目标 KB 中任一项无权时整次请求失败，不返回部分结果，也不静默缩小检索范围。

## 4. 公共约定

- ID 是不透明 UUID 字符串，禁止暴露数据库自增主键或依赖 UUID 排序。
- 时间使用 RFC 3339 UTC，序列化时使用 `Z`；持续时间使用毫秒整数。
- 所有对象都设置 `additionalProperties: false`。
- 文本使用 UTF-8；空白字符串不能满足必填文本字段。
- 数组显式声明最小/最大数量；标识符集合必须去重。
- 可选字段缺失与显式 `null` 是不同语义；仅当 Schema 明确包含 `null` 时才可传空值。
- 分数必须声明范围和含义；Consumer 不比较不同 `score_kind` 的裸值。
- 请求不得携带 `role`、`visibility`、`owner`、`authorized` 或其他调用方计算的授权结论。
- Schema 中的示例只用于解释；`fixtures/` 中的样例才参与自动化验收。

## 5. 版本与协商

Contract 使用 SemVer 字符串，首个发布目标为 `1.0.0`；当前文档只代表 `1.0.0-draft` 设计。Internal Retrieval 请求同时在 `X-EvidSight-Contract-Version` 头和请求体 `contract_version` 中携带已发布版本，两处必须一致；无请求体的 Internal Identity Status 请求只在该请求头携带版本。所有响应回显实际使用的 `contract_version`。Schema、Fixture、生成物以及 Knowledge Provider/Research Consumer 测试全部通过前，任何服务不得宣称支持 `1.0.0`。

版本规则：

1. 任意字段、约束或枚举集合发生变化都发布新的精确版本，不原地修改已发布 Schema。
2. 兼容性修正增加 PATCH；增加可选能力增加 MINOR；删除字段、收紧已发布约束或改变语义增加 MAJOR。
3. Provider 在迁移窗口内同时支持当前版本与一个明确登记的相邻版本。
4. Consumer 只按协商成功的精确版本验证，不以忽略未知字段代替版本协商。
5. 业务层遇到来自其他接口的未知非终态枚举时可映射为 `unknown`；Internal Contract Schema 本身仍严格验证。
6. 服务身份通过后，不支持或头/正文不一致时返回 `INTERNAL_CONTRACT_UNSUPPORTED`，且不进入用户授权或检索。

每次发布必须登记版本、发布日期、Provider 支持窗口、Consumer 最低版本、变更类别和 Fixture 变化。删除旧版本前必须确认所有 Consumer 已切换并通过回归测试。

### 5.1 Internal Identity Status

Research 创建长期任务前调用 `GET /internal/v1/identity/users/{platform_user_id}/status`。Service Token、Contract 版本、`X-Request-ID` 和 W3C Trace Context 属于 HTTP 传输元数据，不进入业务对象。

`IdentityStatusResponse` 字段：

| 字段 | 类型与约束 | 语义 |
|:---|:---|:---|
| `contract_version` | 必填 SemVer | Provider 实际使用的精确版本 |
| `platform_user_id` | 必填 UUID | Knowledge 当前查询的 Platform User ID |
| `status` | `active` | 只有当前可用用户产生成功响应 |
| `status_version` | 非负整数 | Knowledge 权威状态版本；未来状态缓存只能按此版本失效或更新 |

用户不存在和已禁用不产生成功响应，统一使用 `AUTH_USER_DISABLED`。身份数据库不可用使用 `INTERNAL_IDENTITY_UNAVAILABLE`，Consumer 必须失败关闭，不能用历史 `active` 响应继续创建任务。v1.0 Consumer 不缓存该响应；缓存协议不属于当前 Contract。

## 6. Internal Retrieval Request

`RetrievalRequest` 字段：

| 字段 | 类型与约束 | 语义 |
|:---|:---|:---|
| `contract_version` | 必填 SemVer | 与版本头一致 |
| `user_id` | 必填 UUID | Platform User ID；仅作为实时授权主体 |
| `knowledge_base_ids` | 1—50 个唯一 UUID | 所有目标 KB 均需当前 READ 权限 |
| `query` | 1—8192 字符 | 仅用于内部检索，不得自动转发互联网 Provider |
| `purpose` | `research_retrieval` | 防止契约被复用于未审查用途 |
| `limit` | 1—100，默认 20 | 跨全部目标 KB 的最大命中数 |
| `filters` | 可选 `RetrievalFilters` | 只允许已声明的文档 ID、语言和更新时间范围 |

`RetrievalFilters` 不接受 SQL、路径、Collection 名称、任意字段名或任意排序表达式。时间范围必须满足开始时间早于或等于结束时间。Schema 只表达请求能力，具体召回、融合、排序和分数计算由 Knowledge Pipeline 定义。

服务凭证、`X-Request-ID` 和 W3C Trace Context 属于 HTTP 传输元数据，不重复进入请求业务对象。

## 7. Internal Retrieval Response

`RetrievalResponse` 字段：

| 字段 | 类型与约束 | 语义 |
|:---|:---|:---|
| `contract_version` | 必填 SemVer | Provider 实际使用的精确版本 |
| `request_id` | 必填字符串 | 回显跨服务请求关联 ID |
| `results` | `RetrievalHit[]` | 按 Provider 已确定的顺序返回 |
| `returned_count` | 非负整数 | 必须等于 `results` 长度 |
| `has_more` | 布尔值 | 表示当前约束下仍可能存在更多结果 |

空结果是成功响应，不伪造 Evidence。响应不得包含调试信息、内部查询计划、数据库字段、文件路径或缓存信息。

### 7.1 RetrievalHit

`RetrievalHit` 是临时处理对象，不是可持久化 Evidence：

| 字段组 | 必需内容 |
|:---|:---|
| 命中身份 | `hit_id`、`knowledge_base_id`、`document_id`、`document_version_id`、`segment_id` |
| 显示信息 | `document_display_name`、可选 `section_title` |
| 来源位置 | 页码、章节路径或字符区间中的至少一种可解释定位 |
| 临时内容 | `minimal_excerpt`，1—8000 字符 |
| 检索信息 | 至少一个带 `score_kind`、`value` 和排序位置的 `RetrievalScore` |
| 时间信息 | `source_updated_at`、`retrieved_at` |
| 访问范围 | 固定为 `internal` |

`minimal_excerpt` 只允许在当前研究步骤的内存或受控短期执行上下文中使用。它不得进入 Research 业务表、Evidence Graph 持久层、报告、SSE、日志、Trace 或错误详情。执行上下文确需短时保存以支持故障恢复时，必须由 Research Pipeline 另行定义加密、TTL、清理与禁用用户失效语义；本 Contract 不授予默认持久化权。

### 7.2 Internal Evidence Resolve

Research 在 Reranking、Synthesis 或恢复时需要重新取得已经选定的内部候选正文，不得用文本查询猜测原命中。`EvidenceResolveRequest` 包含：

| 字段 | 类型与约束 | 语义 |
|:---|:---|:---|
| `contract_version` | 必填 SemVer | 与版本头一致 |
| `user_id` | 必填 UUID | 当前授权主体 |
| `references` | 1—100 个唯一 `InternalSourceIdentity` | 每项包含 `knowledge_base_id`、`document_id`、`document_version_id`、`segment_id` |
| `purpose` | `research_evidence_resolve` | 禁止复用于其他正文读取 |

`POST /internal/v1/retrieval/resolve` 对每项重新验证用户、KB、Document、Version 和 Segment 的当前可访问性。任一项无权时整批失败；已删除、被替换或不可用但不涉及资源枚举时返回受控 `EVIDENCE_SOURCE_UNAVAILABLE`，不自动改取 Active Version、相邻 Segment 或相似结果。

成功响应按请求顺序返回相同稳定身份、`minimal_excerpt`、安全位置和 `source_updated_at`。正文仍只允许存在于当前 Step 内存，响应不得被持久化。该操作只恢复已经由先前 RetrievalHit 选定的工作集，不执行搜索、排序或生成新 Candidate。

## 8. Evidence Contract

### 8.1 EvidenceReference

`EvidenceReference` 是跨内部/外部来源的可持久化最小引用：

| 字段 | 语义 |
|:---|:---|
| `evidence_id` | 稳定 UUID |
| `source_type` | `internal` 或 `web` |
| `source_identity` | 与来源类型匹配的标识对象 |
| `display` | 可公开给当前任务读者的标题与位置摘要 |
| `captured_at` | Evidence 创建时间 |
| `source_observed_at` | 检索或抓取时观察到的来源时间 |
| `score_summary` | 生成时的受控评分摘要，不作为当前权限或有效性证明 |
| `validity` | `available`、`restricted`、`missing` 或 `stale` |

内部 `source_identity` 必须包含 Knowledge Base、Document、Document Version 和 Segment 的稳定 ID，不得包含正文或可直接访问存储的路径。Document Version 用于解释重处理后的历史来源身份，但不授予旧版本正文访问权；旧版本被清理或不再可访问时返回 `missing` 或 `stale`。外部 `source_identity` 必须包含规范化 URL 和获取时间，不得伪装成内部来源。两类来源字段使用 `oneOf` 严格互斥。

内部 Evidence 可长期保留文档显示名和位置描述，但这不授予原文访问权。展开原文必须调用 Knowledge 来源访问 API 并按当前用户、KB、文档状态重新鉴权。

### 8.2 EvidenceRelation

证据与结论之间使用独立关系对象：

| 字段 | 语义 |
|:---|:---|
| `relation_id` | 稳定 UUID |
| `evidence_id` | 关联 Evidence |
| `claim_id` | 关联结论 |
| `relation_type` | `supports`、`contradicts` 或 `context` |
| `confidence` | 0—1；表示关系判断置信度，不表示来源绝对真实性 |
| `rationale` | 可选安全摘要，不得复制内部原文 |

同一 Evidence 可以关联多个结论。冲突和不确定性由多条关系及 Research Pipeline 的结论规则表达，Contract 不替代状态解析或报告生成算法。

## 9. 临时内容到持久引用的转换门禁

Research 将 `RetrievalHit` 转为 `EvidenceReference` 时必须：

1. 生成或复用稳定 `evidence_id`；
2. 复制稳定来源 ID、显示名、位置、时间和评分摘要；
3. 删除 `minimal_excerpt` 及任何等价正文、Embedding 或 Prompt 副本；
4. 将 `source_type` 固定为 `internal`；
5. 将初始 `validity` 设为转换时的状态，但不把它视为未来访问授权；
6. 在持久化前再次通过 `EvidenceReference` Schema 校验。

Schema 必须从结构上禁止 `EvidenceReference` 出现 `excerpt`、`content`、`text`、`chunk_text`、存储路径或任意扩展字段。转换失败时不得降级保存原始命中对象。

## 10. 错误契约

Internal Contract 错误使用统一信封：

```json
{
  "error": {
    "error_code": "KB_FORBIDDEN",
    "message": "请求的知识库不可访问。",
    "request_id": "01J00000000000000000000000",
    "retryable": false,
    "details": {}
  }
}
```

v1.0 稳定错误码至少包括：

| 错误码 | 可重试 | 语义 |
|:---|:---:|:---|
| `INTERNAL_SERVICE_UNAUTHENTICATED` | 否 | Research 服务身份无效 |
| `INTERNAL_CONTRACT_UNSUPPORTED` | 否 | 版本不支持或版本载体不一致 |
| `INTERNAL_CONTRACT_INVALID` | 否 | 请求不符合已协商 Schema |
| `AUTH_USER_DISABLED` | 否 | 用户不存在、已禁用或不可用于本调用 |
| `INTERNAL_IDENTITY_UNAVAILABLE` | 是 | Knowledge 身份状态事实源暂时不可用 |
| `KB_FORBIDDEN` | 否 | 至少一个目标 KB 当前不可读 |
| `INTERNAL_RATE_LIMITED` | 是 | 内部调用达到受控限额 |
| `INTERNAL_RETRIEVAL_UNAVAILABLE` | 是 | 检索依赖暂时不可用 |
| `EVIDENCE_SOURCE_UNAVAILABLE` | 否 | 指定 Version/Segment 已删除、失效或不可用于当前步骤 |

错误详情只能包含 Schema 明确允许的安全字段。不得包含正文、查询原文回显、凭证、SQL、堆栈、内部路径、Collection 或缓存 Key。认证和授权失败不得泄露目标资源是否存在。

## 11. Fixture 与契约测试

每个 Contract 版本必须提供 Provider 和 Consumer 共用的固定 Fixture。

有效样例至少覆盖：

- active 用户的最小 Identity Status Response；
- 单 KB 与多 KB 请求；
- 单条与批量精确 Evidence Resolve；
- 空结果与多条结果；
- 页码、章节和字符区间位置；
- Internal `EvidenceReference`、Web `EvidenceReference`；
- 三种 Evidence Relation；
- 每一种稳定错误码。

无效样例至少覆盖：

- Identity Status 缺少版本、用户 UUID 或状态版本，以及包含用户名、角色、内部主键或未知字段；
- 未知字段、缺少必填字段和错误类型；
- 版本头与正文不一致、不受支持版本；
- 空 KB 集合、重复 KB、非法 `limit` 和反向时间范围；
- Resolve 身份缺少 Document Version、重复引用或混入查询/排序字段；
- 请求携带角色或授权结论；
- Internal/Web 来源字段混用；
- `EvidenceReference` 包含正文、Embedding、Prompt、文件路径或缓存信息；
- 未知关系枚举、越界置信度和不安全错误详情。

Knowledge Provider 测试必须证明其响应符合 Schema；Research Consumer 测试必须证明其能消费全部有效 Fixture，并拒绝无效 Fixture。双方不得使用各自复制的样例替代本包 Fixture。

## 12. CI 与发布门禁

Contract 变更必须依次通过：

1. JSON Schema 2020-12 Meta-Schema 校验；
2. 所有 `$id` 唯一、所有 `$ref` 可解析；
3. 有效/无效 Fixture 的预期结果；
4. Python/Pydantic 与 TypeScript 生成；
5. 重新生成后无工作区差异；
6. Knowledge Provider 与 Research Consumer 契约测试；
7. 版本兼容矩阵和迁移窗口检查；
8. 禁止服务实现依赖和敏感字段的静态扫描。

上述门禁按“当前已登记的生成 target”执行生成物复现与差异检查。当前 Python/Pydantic 参考生成物已入库，但仓库内尚无可重复生成命令；TypeScript 生成链亦仍处于未实现状态。两者都不得将缺席视为通过。Python/Pydantic 复现命令与基础 CI 同步补齐；TypeScript 生成链在 M4 落地时必须与复现命令和“重新生成后无差异”检查同步登记。每个 target 从登记之时起成为 Contract 变更的必过项。

基础 CI 只读执行本节已可执行的门禁，不回写生成物或自动提交。Provider 契约测试按 [TESTING.md §4](../../docs/specs/TESTING.md#4-contract-门禁) 在受管服务容器中执行，但基础 CI 不因此启动 MySQL、Redis、Celery 或 Chroma。

发布 Contract 不代表对应服务已经实现或上线。只有 Provider、Consumer、权限拒绝、版本拒绝和端到端 Internal Retrieval 验收全部通过后，才能声明该版本可用。

## 13. 验收场景

1. 合法 Research 服务以已发布 Contract 版本查询 active 用户，只得到最小身份状态响应；禁用、不存在或身份库不可用时失败关闭。
2. 合法 Research 服务以已发布 Contract 版本请求用户当前可读 KB，双方使用同一 Schema 成功交换结果。
3. 未认证服务、禁用用户或任一 KB 无权时，在检索前失败且不返回部分 Evidence。
4. 服务身份通过后，不支持版本或版本载体不一致时返回稳定错误，不进入用户授权与检索。
5. Knowledge 返回的每个 `RetrievalHit` 都可定位来源，且不暴露内部实现标识。
6. Research 转换并持久化的 `EvidenceReference` 不含内部正文，展开原文仍需 Knowledge 实时鉴权。
7. Internal/Web 来源字段互斥，错误归类或混用无法通过 Schema。
8. Evidence Relation 能表达支持、反对和背景，并允许一条 Evidence 关联多个结论。
9. 所有未知字段和未知 Contract 枚举均被严格拒绝。
10. 生成物可重复生成，Provider/Consumer 使用共同 Fixture 且结果一致。
11. 文档、Schema、Fixture 和生成物不包含服务内部模型、路径、缓存键或敏感正文。
12. Research 可以按完整 KB/Document/Document Version/Segment 身份精确重取当前可访问正文，且不会静默切换版本或产生新候选。

## 14. 后续实施边界

Contract 当前为 `1.0.0-draft` 设计阶段，Schema 与 Fixture 覆盖如下（2026-08-04 状态）：

- **Internal Identity Status**（2026-08-03）：`common.schema.json`、`identity-status-response.schema.json`、`error-response.schema.json`；identity-status-response（1 valid / 12 invalid）与 error-response（2 valid / 3 invalid）Fixture。
- **Internal Retrieval & Evidence**（2026-08-04，M2）：`retrieval-request/response.schema.json`、`retrieval-hit.schema.json`、`evidence-resolve-request/response.schema.json`、`evidence-reference.schema.json`、`evidence-relation.schema.json`；`common.schema.json` 扩展 `Timestamp`/`ScoreKind`/`UnitInterval`/`InternalSourceIdentity`/`SourceLocation`；`error-response.schema.json` 扩展 `KB_FORBIDDEN`/`INTERNAL_RATE_LIMITED`/`INTERNAL_RETRIEVAL_UNAVAILABLE`/`EVIDENCE_SOURCE_UNAVAILABLE`。落地 24 valid / 50 invalid Fixture 与共享语义不变量 `generated/python/evidsight_contracts/semantics.py`（跨字段约束：`returned_count == len(results)`、`updated_since <= updated_until`、`source_type` 与来源身份匹配）。

`generated/python/evidsight_contracts/` 包含参考 Pydantic 模型与 `loader.py`（`$ref` 文件系统解析 + `referencing.Registry`）。契约自检 `packages/contracts/tests/` 覆盖 Meta-Schema、`$ref` 解析、Fixture 正反校验、语义不变量与 Pydantic 参考模型 smoke。Knowledge Provider 契约测试（`services/knowledge/tests/contract/`）与 Research Consumer 契约测试（`services/research/tests/contract/`）覆盖 Identity Status 与 Retrieval/Evidence 两套契约；Provider 端点级（`/internal/v1/retrieval/search` 与 `/resolve`）验收已由权限感知 Provider 切片落地（21 项，按 §3 固定处理顺序校验，命中对象仅含契约字段，2026-08-04）。

TypeScript 生成物、`datamodel-code-generator`/`json-schema-to-typescript` 生成器配置留给 M4 React/TS 与 CI 工具链就绪后补齐；届时重新生成并核对「重新生成后无工作区差异」。

下一步由 Knowledge/Research 专项规范分别定义 Provider 与 Consumer 的业务实现。任何需要改变本文服务边界、正文持久化策略、版本兼容规则或授权顺序的实现，都必须先修订本设计；涉及安全、数据生命周期或跨服务职责变化时同时新增 ADR。
