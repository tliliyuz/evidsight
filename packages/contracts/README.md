# EvidSight 跨服务契约设计

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认设计 |
| 文档版本 | v1.0 |
| Contract 基线 | `1.0.0` |
| 最后更新 | 2026-07-31 |

> 本文是 `packages/contracts/` 的权威设计入口。HTTP 路由、认证载体和状态码由 [`docs/API.md`](../../docs/API.md) 定义，身份与实时授权由 [`docs/IDENTITY_AND_ACCESS.md`](../../docs/IDENTITY_AND_ACCESS.md) 定义，服务边界由 [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) 定义。本文只定义跨服务纯数据 Schema、版本规则与契约测试。

## 1. 目标与边界

本包使 Knowledge Service 与 Research Service 可以独立实现和部署，并通过可执行契约验证双方对 Internal Retrieval 和 Evidence 的理解一致。

v1.0 只包含：

- Internal Retrieval Request/Response；
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
│       ├── retrieval-request.schema.json
│       ├── retrieval-response.schema.json
│       ├── retrieval-hit.schema.json
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

Contract 使用 SemVer 字符串，首个基线为 `1.0.0`。Internal Retrieval 请求同时在 `X-EvidSight-Contract-Version` 头和请求体 `contract_version` 中携带版本，两处必须一致；响应回显实际使用的 `contract_version`。

版本规则：

1. 任意字段、约束或枚举集合发生变化都发布新的精确版本，不原地修改已发布 Schema。
2. 兼容性修正增加 PATCH；增加可选能力增加 MINOR；删除字段、收紧已发布约束或改变语义增加 MAJOR。
3. Provider 在迁移窗口内同时支持当前版本与一个明确登记的相邻版本。
4. Consumer 只按协商成功的精确版本验证，不以忽略未知字段代替版本协商。
5. 业务层遇到来自其他接口的未知非终态枚举时可映射为 `unknown`；Internal Contract Schema 本身仍严格验证。
6. 服务身份通过后，不支持或头/正文不一致时返回 `INTERNAL_CONTRACT_UNSUPPORTED`，且不进入用户授权或检索。

每次发布必须登记版本、发布日期、Provider 支持窗口、Consumer 最低版本、变更类别和 Fixture 变化。删除旧版本前必须确认所有 Consumer 已切换并通过回归测试。

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
| 命中身份 | `hit_id`、`knowledge_base_id`、`document_id`、`segment_id` |
| 显示信息 | `document_display_name`、可选 `section_title` |
| 来源位置 | 页码、章节路径或字符区间中的至少一种可解释定位 |
| 临时内容 | `minimal_excerpt`，1—8000 字符 |
| 检索信息 | 至少一个带 `score_kind`、`value` 和排序位置的 `RetrievalScore` |
| 时间信息 | `source_updated_at`、`retrieved_at` |
| 访问范围 | 固定为 `internal` |

`minimal_excerpt` 只允许在当前研究步骤的内存或受控短期执行上下文中使用。它不得进入 Research 业务表、Evidence Graph 持久层、报告、SSE、日志、Trace 或错误详情。执行上下文确需短时保存以支持故障恢复时，必须由 Research Pipeline 另行定义加密、TTL、清理与禁用用户失效语义；本 Contract 不授予默认持久化权。

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

内部 `source_identity` 必须包含 Knowledge Base、Document 和 Segment 的稳定 ID，不得包含正文或可直接访问存储的路径。外部 `source_identity` 必须包含规范化 URL 和获取时间，不得伪装成内部来源。两类来源字段使用 `oneOf` 严格互斥。

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
| `KB_FORBIDDEN` | 否 | 至少一个目标 KB 当前不可读 |
| `INTERNAL_RATE_LIMITED` | 是 | 内部调用达到受控限额 |
| `INTERNAL_RETRIEVAL_UNAVAILABLE` | 是 | 检索依赖暂时不可用 |

错误详情只能包含 Schema 明确允许的安全字段。不得包含正文、查询原文回显、凭证、SQL、堆栈、内部路径、Collection 或缓存 Key。认证和授权失败不得泄露目标资源是否存在。

## 11. Fixture 与契约测试

每个 Contract 版本必须提供 Provider 和 Consumer 共用的固定 Fixture。

有效样例至少覆盖：

- 单 KB 与多 KB 请求；
- 空结果与多条结果；
- 页码、章节和字符区间位置；
- Internal `EvidenceReference`、Web `EvidenceReference`；
- 三种 Evidence Relation；
- 每一种稳定错误码。

无效样例至少覆盖：

- 未知字段、缺少必填字段和错误类型；
- 版本头与正文不一致、不受支持版本；
- 空 KB 集合、重复 KB、非法 `limit` 和反向时间范围；
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

发布 Contract 不代表对应服务已经实现或上线。只有 Provider、Consumer、权限拒绝、版本拒绝和端到端 Internal Retrieval 验收全部通过后，才能声明该版本可用。

## 13. 验收场景

1. 合法 Research 服务以 `1.0.0` 请求用户当前可读 KB，双方使用同一 Schema 成功交换结果。
2. 未认证服务、禁用用户或任一 KB 无权时，在检索前失败且不返回部分 Evidence。
3. 服务身份通过后，不支持版本或版本载体不一致时返回稳定错误，不进入用户授权与检索。
4. Knowledge 返回的每个 `RetrievalHit` 都可定位来源，且不暴露内部实现标识。
5. Research 转换并持久化的 `EvidenceReference` 不含内部正文，展开原文仍需 Knowledge 实时鉴权。
6. Internal/Web 来源字段互斥，错误归类或混用无法通过 Schema。
7. Evidence Relation 能表达支持、反对和背景，并允许一条 Evidence 关联多个结论。
8. 所有未知字段和未知 Contract 枚举均被严格拒绝。
9. 生成物可重复生成，Provider/Consumer 使用共同 Fixture 且结果一致。
10. 文档、Schema、Fixture 和生成物不包含服务内部模型、路径、缓存键或敏感正文。

## 14. 后续实施边界

下一步先建立 `schemas/v1/`、Fixture、生成器配置和契约测试，再由 Knowledge/Research 专项规范分别定义 Provider 与 Consumer 的业务实现。任何需要改变本文服务边界、正文持久化策略、版本兼容规则或授权顺序的实现，都必须先修订本设计；涉及安全、数据生命周期或跨服务职责变化时同时新增 ADR。
