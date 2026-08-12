# 据见（EvidSight）统一身份与访问控制规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | 已确认规范 |
| 文档版本 | v1.0 |
| 最后更新 | 2026-08-03 |
| 适用范围 | Web、Knowledge Service、Research Service 与内部服务调用 |

> 本文是统一身份、令牌、服务认证、授权上下文和敏感数据外发策略的权威规范。产品角色与权限矩阵见 [PRD.md](PRD.md) §8；服务所有权与网络信任边界见 [ARCHITECTURE.md](ARCHITECTURE.md)；HTTP 路由、状态码和错误码见 [API.md](API.md)。本文不定义数据库字段或业务 API Schema。

## ADR 检查

- 检查日期：2026-08-02
- 检查结果：第 1、6、8 项为否；第 2、3、4、5、7 项为是。
- 命中原因：统一身份改变跨服务信任边界和身份契约；服务认证与敏感数据外发属于长期安全机制；决策共同影响身份、API、配置、数据库和 Contract 规范。
- 裁决：负责人于 2026-08-02 明确接受 [ADR-005](../decisions/ADR-005-unified-identity-service-auth-egress.md)，当前状态为 `accepted`。
- 门禁：现在可以从本规范导出验收测试；生产实现仍须先观察对应验收测试因目标行为缺失而正确 RED。

Refresh Token Cookie/CSRF 收口检查：

- 检查日期：2026-08-03
- 检查结果：ADR 检查 3、4、7 为是（公共契约、数据与安全、跨规范影响），1、2、5、6、8 为否。
- 理由：Refresh Token 从响应体迁移到 HttpOnly Cookie + double-submit CSRF 会改变外部认证 API 契约（`login`/`refresh` 不再返回明文、`refresh`/`logout` 新增必需 `X-CSRF-Token`）、敏感信息存储与传输边界（localStorage → HttpOnly Cookie）、部署/跨域配置（Origin 白名单、SameSite），并需同步修改 Auth、Frontend、Testing、API、CONFIGURATION 五份规范。ADR-005 只裁决统一身份、服务认证与数据外发，未裁决浏览器传输载体，故不能视为 ADR-005 已接受基线。
- 裁决：负责人于 2026-08-03 明确接受 [ADR-006](../decisions/ADR-006-refresh-token-cookie-csrf.md)，当前状态为 `accepted`。
- 门禁：可以更新 Auth、Frontend、Testing 和 Knowledge API 规范，并从 IA-015/IA-016 导出 RED 测试；生产实现不得在 RED 前开始。

禁用用户全链路测试补齐检查（IA-005）：

- 检查日期：2026-08-04
- 检查结果：ADR 检查 1–8：否
- 理由：本次补齐 §6 已定义的禁用用户失败语义（新建 Chat、上传、重处理和治理写操作失败）的 API 层验收测试，并同步 TESTING.md §3.2 测试矩阵与 §13 IA-005 场景表述；不改变既有 accepted ADR、服务边界、公共契约、权限模型或鉴权时机，不构成不可逆决定或长期例外。
- 门禁：已确认 §6 覆盖目标行为，可从 §6 导出验收测试；目标行为由 `get_current_user` 既有实现满足，负向验证确认测试可检测禁用检查缺失，GREEN 无生产代码修改。

签名密钥轮换验收测试补齐检查（IA-010）：

- 检查日期：2026-08-04
- 检查结果：ADR 检查 1–8：否
- 理由：本次为 §12 已定义的密钥轮换规则（先发布新验证材料，再切换签发，等待旧 Token 最大有效期结束后移除旧材料；支持 Key ID 与受控双 Key 验证窗口）补齐 Service JWT 双 Key 窗口验收测试；不改变既有轮换策略、公共契约或安全基线，无新方案选择，不构成不可逆决定或长期例外。
- 门禁：已确认 §12 覆盖目标行为，可从 §12 导出验收测试；目标行为由 `verify_service_token` 多 Key 映射既有实现满足，负向验证确认测试可检测轮换窗口支持缺失，GREEN 无生产代码修改。

知识库权限矩阵验收测试补齐检查：

- 检查日期：2026-08-04
- 检查结果：ADR 检查 1–8：否
- 理由：本次为 PRD §8.2 已确认的知识库权限矩阵补齐纯函数级验收测试（`test_permissions.py`），覆盖 READ（visibility 优先）、WRITE（ownership 基础、admin 治理）与 owner-only（上传文档）语义；不改变既有权限模型、鉴权时机、公共契约或安全基线，无新方案选择，不构成不可逆决定或长期例外。
- 门禁：已确认 PRD §8.2 与 §8 执行规则覆盖目标行为，可从矩阵导出验收测试；目标行为由 `require_kb_readable`/`require_kb_writable`/`require_kb_owner` 既有实现满足，负向验证确认测试可检测权限分支缺失，GREEN 无生产代码修改。

M1 退出门禁 6 负向日志测试补齐检查：

- 检查日期：2026-08-04
- 检查结果：ADR 检查 1–8：否
- 理由：本次为 §11 已定义的"日志不记录密码、Token、服务凭证"约束补齐负向验收测试（登录成功/失败路径日志均不含密码与 Access/Refresh Token 明文），并纳入 M1 退出门禁核对；不改变既有日志格式、鉴权时机、公共契约或安全基线，无新方案选择，不构成不可逆决定或长期例外。
- 门禁：已确认 §11 覆盖目标行为，可从 §11 导出验收测试；目标行为由 `auth_service` 既有实现满足（登录成功仅记录 user_id，失败不记录请求凭证），负向验证确认注入密码日志时测试正确 RED，GREEN 无生产代码修改。

## 1. 目标与边界

本设计保证用户在知识中心、据见问答、深度研究、报告和管理中心之间使用同一身份，同时不把统一登录误解为跨服务共享数据库或无条件互信。

必须满足：

- Platform User ID 是跨服务唯一、稳定且不可从用户名推导的用户标识；
- Knowledge Service 的身份模块负责认证入口、令牌签发、刷新和撤销；
- Research Service 只验证 Access Token，不签发或持久化 Refresh Token；
- 服务身份与终端用户授权分别验证，任何一项缺失都不能访问 Internal Retrieval；
- 管理员治理、资源所有权和知识库可见性分别判断；
- 内部证据原文每次打开都按当前权限复核；
- 私有知识外发默认拒绝，允许外发必须有配置、脱敏和审计依据。

v1.0 不建立独立 Identity Service，不支持企业 SSO、SAML、SCIM、部门角色或完整 ACL。

## 2. 身份主体与信任关系

| 主体 | 身份来源 | 信任范围 | 明确不授予 |
|:---|:---|:---|:---|
| 浏览器用户 | Access Token | 当前用户身份和系统角色 | 对任意资源的访问权 |
| Knowledge Service | 部署身份与最小权限数据库账号 | Auth、Knowledge、Chat 及 Internal Retrieval Provider | Research 数据访问权 |
| Research Service | 部署身份、服务凭证与最小权限数据库账号 | Research 业务及 Internal Retrieval Consumer | Knowledge 数据库或向量存储访问权 |
| 管理员 | 用户 Access Token 中的 `admin` 角色 | PRD 权限矩阵规定的审计和治理操作 | 替普通用户上传文档或绕过实时证据权限 |
| 外部 Provider | 独立 Provider 凭证 | 被策略允许的单次模型、搜索或抓取请求 | 对内部网络、数据库或完整用户身份的访问 |

Platform User ID 使用 UUID 字符串对外表达。所有外部 User DTO 的 `id` 字段都表示 Platform User ID；用户名、邮箱、显示名和数据库自增主键都不能替代 Platform User ID 作为跨服务关联键。迁移期 Knowledge 内部 `users.id` 仍可服务旧表关系，但不得进入 `/api/v1/*` 响应、SSE、Research Contract 或前端身份状态。

系统角色仅有 `user` 与 `admin`。业务画像不产生额外角色；资源能力由角色、所有权、可见性、资源状态和操作类型共同决定。

## 3. Access Token

### 3.1 必需 Claims

| Claim | 语义 | 验证要求 |
|:---|:---|:---|
| `iss` | 统一签发方 | 必须等于部署配置的固定 Issuer |
| `aud` | 允许的服务受众 | Knowledge 与 Research 分别验证自己是合法 Audience |
| `sub` | Platform User ID | 必须是合法 UUID 字符串 |
| `role` | `user` 或 `admin` | 未知角色拒绝，不默认降级 |
| `token_type` | 固定为 `access` | Refresh Token 不得调用业务接口 |
| `jti` | Token 唯一标识 | 用于审计、撤销与异常关联 |
| `iat` | 签发时间 | UTC NumericDate，不得明显晚于当前时间 |
| `nbf` | 生效时间 | 当前时间早于该值时拒绝 |
| `exp` | 过期时间 | 过期立即拒绝 |

Claims 只能携带稳定身份语义，不嵌入知识库列表、资源权限快照或私有业务数据；不得携带 `username` 等可派生展示字段，显示信息（用户名、角色、状态）必须由服务端从数据库当前状态读取。资源权限必须在服务端实时计算。

### 3.2 签名与验证

- JWT Algorithm、Issuer、Audience、允许的时钟偏差和有效期来自配置 Schema；不得在业务代码硬编码。
- 验证器使用算法允许列表，禁止根据 Token Header 自动接受任意算法，禁止 `none`。
- 两个服务使用相同 Claim 语义和时间规则；密钥通过部署 Secret 注入，不写入仓库、日志或错误响应。
- Access Token 的 `aud` 是包含 `evidsight-knowledge` 与 `evidsight-research` 的数组；Knowledge 与 Research 分别从自己的配置读取期望 Audience，并只接受数组中包含自身 Audience 的 Token。
- 每个受保护请求验证签名、算法、Issuer、Audience、`token_type`、必需 Claims 和时间窗口。
- Claim 缺失、类型错误、签名失败和过期统一映射为安全认证错误（401），不向客户端区分密码、密钥或验证器内部细节。Token 自身 `exp` 已过是客户端可观测状态，返回明确的「已过期」认证错误（`AUTH_TOKEN_EXPIRED`），供前端静默刷新续期；其余验证失败返回「无效」认证错误（`AUTH_TOKEN_INVALID`）。ADR 检查 1–8：否（记录见 CHANGELOG，2026-08-12）。

Access Token 应采用分钟级短有效期。精确默认值由部署配置权威定义；改变有效期不得改变已签发 Token 的 `exp`，并必须评估禁用传播延迟和刷新压力。

### 3.3 用户状态复核

仅验证 JWT 不能保证用户当前仍启用。以下操作必须查询权威用户状态或使用有明确短 TTL、支持主动失效的状态缓存：

- 登录与刷新；
- 创建研究任务、上传或重新处理文档；
- 管理员治理操作；
- Internal Retrieval；
- 打开内部证据原文；
- 其他会产生长期结果、外部调用或敏感数据读取的操作。

普通只读请求可以在 Access Token 短有效期内使用受控状态缓存，但禁用事件必须主动失效两个服务中的相关缓存。

## 4. Refresh Token

Refresh Token 只由 Knowledge Auth API 接收和处理，Research Service、URL 查询参数、日志和前端持久业务状态均不得接触其明文。

### 4.1 存储与轮换

- 数据库只保存 Refresh Token 的抗离线破解哈希、`jti`、Platform User ID、Token Family、签发/过期/撤销时间和必要审计元数据。
- 每次成功刷新必须签发新的 Access Token 和 Refresh Token，并在同一事务中撤销旧 Refresh Token。
- 已轮换 Token 再次出现视为重放：撤销整个 Token Family，记录安全审计事件，并要求用户重新登录。
- 并发刷新只允许一个请求成功；其余请求按已轮换或冲突处理，不能生成多个有效后继。
- 退出登录撤销当前 Token Family；管理员禁用用户时撤销该用户全部 Token Family。

### 4.2 浏览器传输

浏览器目标态必须使用 `HttpOnly`、`Secure`、适当 `SameSite` 的 Cookie 保存 Refresh Token，并使用 CSRF 防护。Refresh Token 禁止进入 URL、SSE、Analytics、普通应用日志、Local Storage、Session Storage、IndexedDB、可读 Cookie 或前端业务状态。

Cookie 模式采用以下规则：

- Refresh Cookie 仅由 Knowledge Auth API 设置、轮换和清除，名称由配置定义，生产环境必须使用 `__Host-` 前缀、`Path=/`、`HttpOnly`、`Secure`、`SameSite=Lax`；跨站部署需要 `SameSite=None; Secure` 时，必须同时启用严格 Origin 校验。`Path=/` 是 `__Host-` 前缀的强制要求（RFC 6265bis §5.5）；Cookie 仍只被 `/api/v1/auth/refresh` 与 `/api/v1/auth/logout` 作为凭据读取，其他业务接口不得将其作为认证凭据。（2026-08-03 文档裁决方案 A 更正 Path）
- 登录成功创建 Token Family 后设置 Refresh Cookie；刷新成功必须在同一响应中设置新的 Refresh Cookie；退出、重放检测、Token Family 撤销和用户禁用后的刷新失败必须清除 Refresh Cookie。
- Access Token 仍在响应体返回，由前端保存在内存或受控短期状态中并通过 `Authorization: Bearer` 调用业务 API；Access Token 不得写入长期可读持久存储。
- Cookie 只用于 `/api/v1/auth/refresh` 与 `/api/v1/auth/logout`，不得被 Chat、Research、SSE、Internal API 或其他业务接口作为认证凭据。

CSRF 采用 double-submit 模式：Knowledge Auth API 同时设置一个非 `HttpOnly` 的 CSRF Cookie，前端在刷新和退出请求中回传同值 `X-CSRF-Token` Header。服务端必须在执行任何 Refresh Token 解码、哈希查询、轮换或撤销前完成 CSRF 校验；Header 缺失、Cookie 缺失、值不一致或 Origin 不在允许列表时返回安全认证错误，且不得改变 Token Family 或写入重放审计。

迁移期允许后端继续接受 JSON Body 中的 `refresh_token`，但仅作为旧 Web 调用兼容入口。兼容入口必须受配置开关控制、记录不含 Token 的弃用调用量，并在观测窗口归零后删除；前端目标态不得再读取、写入或传递 Body refresh_token。若部署明确选择响应体模式作为长期例外，必须在本规范重新完成 ADR 检查并在前端安全设计中记录 XSS 风险、退出清理和禁用传播影响。

## 5. 登录、刷新与退出

### 5.1 登录

1. Knowledge Auth API 对登录入口限流。
2. 按固定耗时策略校验凭证，用户不存在与密码错误使用同一公开错误。
3. 检查用户启用状态。
4. 在数据库事务中创建 Refresh Token Family。
5. 签发 Access/Refresh Token，设置 Refresh Cookie 与 CSRF Cookie，记录成功审计，返回 Access Token 和最小用户摘要；目标态响应体不得包含 Refresh Token 明文。

认证失败不得暴露用户是否存在、密码哈希、Token、数据库异常或堆栈。

### 5.2 刷新

1. 先校验 CSRF 与 Origin；校验失败不得读取或改变 Refresh Token 状态。
2. 从 Refresh Cookie 读取 Refresh Token；迁移期可在配置允许时回退读取 JSON Body。
3. 验证 Refresh Token 格式、哈希、类型、过期和撤销状态。
4. 锁定当前 Token 或使用等价 CAS，避免并发双花。
5. 重新检查用户启用状态。
6. 轮换 Token，并在同一事务中提交旧 Token 撤销和新 Token 创建。
7. 设置新的 Refresh Cookie 与 CSRF Cookie，返回新 Access Token；事务失败时不得留下两个有效后继。

### 5.3 退出

退出是幂等操作。服务先校验 CSRF 与 Origin；校验通过后撤销能够识别的当前 Token Family，清除 Refresh Cookie 与 CSRF Cookie，并返回成功；重复退出不得泄露 Token 是否曾有效。前端同时清除 Access Token、用户信息、Chat/Research 订阅和敏感页面状态。

## 6. 用户禁用语义

管理员禁用用户后：

- 新登录和刷新立即失败；
- 全部 Refresh Token Family 被撤销；
- 两个服务的用户状态缓存立即失效；
- 新建 Chat、Research、上传、重处理和治理写操作失败；
- Internal Retrieval 和内部证据原文访问失败；
- 正在运行的研究任务收到禁用信号后进入受控取消或失败，不再发起新的内部检索、外部搜索或模型调用；
- 已完成报告和审计轨迹保留，但被禁用用户不能访问；管理员按治理权限审计；
- 恢复启用不会自动恢复旧 Refresh Token 或被终止任务，用户必须重新登录，任务按 Research 规范重新创建或恢复。

短期 Access Token 不能被视为禁用后的永久通行证。对无法立即查询用户状态的普通只读请求，最大残余访问窗口不得超过 Access Token 有效期或状态缓存 TTL 中更短者。

## 7. 服务间认证与用户授权上下文

Research Service 调用 Knowledge Internal Retrieval 时必须同时提供：

1. 可验证的 Research 服务身份；
2. 终端用户 Platform User ID；
3. 请求 ID 与调用链 ID；
4. 目标知识库 ID 集合；
5. Internal Contract 版本。

服务身份采用可轮换的短期服务 Token 或等价的双向认证机制，具体载体由部署与 API 规范定义。服务凭证不得复用用户 JWT，不得包含长期静态管理员权限，也不得授予任何知识库 READ 权限。

Knowledge Service 的校验顺序为：

```text
内部网络边界
  → Research 服务身份
  → Contract 版本与请求完整性
  → 用户存在且启用
  → 每个目标 KB 当前 READ 权限
  → 检索与 Evidence 返回
```

任一步失败都不得执行后续检索。Research 传入的角色、可见性、owner 或“已授权”结论不作为授权依据；Knowledge 使用自己的权威数据重新计算权限。

## 8. 资源授权规则

产品级操作矩阵以 [PRD.md](PRD.md) §8 为准。本节只定义执行规则：

- `visibility` 决定知识库 READ，所有权与管理员治理权限决定 WRITE；不得合并为单一 `is_admin_or_owner` 判断。
- 管理员对知识库和研究任务的能力是审计与治理覆盖，不自动获得所有 owner-only 业务能力。
- 研究任务默认只有创建者可读写；管理员可按治理权限查看、取消、恢复或删除。
- 研究任务保存所选 KB ID，但每次内部检索仍重新校验当前权限。
- 列表查询必须在数据库查询层应用可见范围，不能先取全量再在应用层过滤。
- 批量操作逐个资源授权；任一失败时使用 API 文档规定的原子或部分失败语义，不静默跳过。
- 防资源枚举的端点可把无权限隐藏为 `404`，但同一资源类型必须保持一致，并在 API 文档明确。

## 9. 内部证据实时复核

报告中的内部 Evidence 可以长期保留以下最小历史信息：稳定 Evidence ID、来源类型、文档显示名、位置描述、引用关系、生成时评分和生成时间。该历史记录不授予原文访问权。

用户展开内部证据原文时：

1. Web 向 Knowledge Service 请求来源位置；
2. Knowledge 读取当前用户状态、KB 状态和 READ 权限；
3. 权限有效时返回最小必要片段和定位信息；
4. 权限撤销、文档删除或来源失效时返回明确受限/不可用状态；
5. Research 报告不得以内嵌历史正文作为绕过路径。

管理员查看原文同样必须走管理审计权限并记录审计事件。报告导出若包含内部原文，必须在导出时再次鉴权并标注敏感性；v1.0 的正式导出属于 P1。

## 10. 敏感数据外发策略

### 10.1 默认规则

- 内部文档正文、分块、用户问题中的内部信息和内部 Evidence 默认不得进入互联网搜索词。
- `hybrid` 研究必须分别生成内部检索查询和外部搜索查询；不得把内部检索结果自动拼接到外部查询。
- 私有内容发送外部 LLM 默认拒绝。部署策略必须显式允许具体数据分类、Provider、用途和环境后才可外发。
- 无法确认来源分类、Provider 能力或策略结果时失败关闭。

### 10.2 决策流程

```text
识别来源与数据分类
  → 判断目标 Provider 和用途
  → 匹配显式允许策略
  → 最小化与脱敏
  → 记录审计摘要
  → 发起外部调用
```

最小化要求删除与任务无关的段落、凭证、个人敏感信息和内部标识；可用摘要、实体占位符或局部片段满足目的时，不发送完整正文。

### 10.3 审计内容

外发审计记录用户、任务、Provider、模型/搜索能力、数据分类、用途、策略版本、脱敏结果摘要、时间、请求 ID 和允许/拒绝结果。审计记录不得保存凭证或无必要的完整正文。

## 11. 审计与可观察性

至少记录以下安全事件：

- 登录成功与失败、限流；
- Refresh 成功、过期、撤销和重放；
- 退出与管理员启用/禁用；
- 管理员治理操作及原因；
- Internal Retrieval 的服务认证失败、用户禁用和 KB 越权；
- 内部证据原文允许/拒绝；
- 敏感数据外发允许/拒绝和策略版本；
- 密钥轮换及验证异常。

所有事件携带 `request_id`，跨服务时传播调用链 ID。日志不记录密码、Token、服务凭证、完整私有正文、SQL、内部路径或堆栈到公开响应。安全审计的保留期、访问角色和脱敏规则由部署与治理配置明确。

## 12. 密钥轮换、兼容与失败

- JWT 签名密钥和服务凭证必须支持标识当前 Key ID，并允许受控的双 Key 验证窗口。
- 轮换先发布新验证材料，再切换签发，等待旧 Token 最大有效期结束后移除旧材料。
- 验证材料加载失败时服务 readiness 失败；不得退回不验签或接受任意算法。
- 两个服务的 Claim 语义属于兼容契约。新增可选 Claim 可向后兼容；删除必需 Claim、改变 `sub`/`role` 含义或 Audience 属于 Breaking Change。
- 服务凭证失效时 Internal Retrieval 失败并可安全重试；不得降级为匿名或管理员调用。
- 身份数据库不可用时登录、刷新和需要实时状态复核的敏感操作失败关闭；已验证的普通请求是否短暂服务取决于明确的状态缓存策略。

## 13. 验收场景

| 编号 | 场景 | 预期结果 |
|:---|:---|:---|
| IA-001 | 用户登录后调用 Knowledge 与 Research | 两个服务识别为同一 Platform User ID 和角色 |
| IA-002 | Token Algorithm、Issuer、Audience、类型或时间无效 | 请求被拒绝，不暴露验证细节 |
| IA-003 | 使用有效 Refresh Token 刷新 | 旧 Token 撤销，仅新后继有效 |
| IA-004 | 重放已轮换 Refresh Token | 整个 Token Family 撤销并记录安全事件 |
| IA-005 | 管理员禁用用户 | 登录、刷新、新任务、Chat、上传、重处理、治理写操作、内部检索和原文访问均失败 |
| IA-006 | Research 服务凭证有效但用户无 KB 权限 | Knowledge 拒绝，不执行检索 |
| IA-007 | 报告完成后撤销用户 KB 权限 | 报告历史引用可见，内部原文不可展开 |
| IA-008 | `hybrid` 任务包含私有内部内容 | 内部内容不进入互联网搜索词 |
| IA-009 | 外部 LLM 未获私有内容外发许可 | 调用失败关闭并记录策略拒绝 |
| IA-010 | 签名密钥轮换 | 窗口内按 Key ID 验证新旧 Token，窗口后旧 Key 失效 |
| IA-011 | 用户并发刷新同一 Token | 至多一个请求成功，不产生两个有效后继 |
| IA-012 | Internal Retrieval 缺少服务身份或用户上下文 | 请求被拒绝且不返回 Evidence |
| IA-013 | Access Token Claim 不含展示字段 | 用户名、角色和状态从 `/api/v1/auth/me` 当前状态读取 |
| IA-014 | 调用 `/api/v1/auth/me` | 返回 Platform User UUID 摘要，禁用/不存在统一拒绝 |
| IA-015 | Cookie 模式刷新和退出 | Refresh Token 只在 HttpOnly Cookie 中传输，CSRF/Origin 失败不改变 Token 状态 |
| IA-016 | 旧 Body Refresh Token 迁移期调用 | 仅配置允许时兼容并记录弃用用量；目标态前端不再持久化或提交 Refresh Token 明文 |
| IA-017 | 外部 User DTO 与旧 Auth 接口退出 | User DTO `id` 为 Platform User UUID；旧 `/api/auth/*` 与 `id=int` UserResponse 按观测窗口退出 |

以上场景必须转化为 Auth、Research、Internal Retrieval 的自动化验收测试；涉及外发的数据泄露场景同时检查请求载荷和日志。
