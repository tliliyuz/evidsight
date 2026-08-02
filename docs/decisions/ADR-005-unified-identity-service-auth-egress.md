# ADR-005：统一身份、服务认证与敏感数据外发策略

- 状态：accepted
- 日期：2026-08-02
- 里程碑：M1
- 命中的 ADR 检查项：2、3、4、5、7

## 背景

M1 需要让 Knowledge Service 与 Research Service 对同一 Platform User ID、JWT Claims、禁用状态和资源权限得到一致结论，同时为 Internal Retrieval 建立不能由终端用户伪造的服务身份。Research 的 `hybrid` 路径还可能同时接触企业内部内容与外部搜索、模型 Provider，因此必须在生产实现前固定敏感数据外发边界。

这些选择共同影响服务信任边界、公共身份语义、密钥轮换、审计、跨服务 Contract，以及 Knowledge、Research 和 Web 的失败行为。仅在各模块中分别实现会产生不一致且难以审查的长期约束。

## 决策

### 统一用户身份

- Knowledge Service 管理 `platform_db` 中的用户、Refresh Token Family、启禁用状态和身份审计，并作为 Access/Refresh Token 的唯一签发方。
- Research Service 不签发 Access Token、不接收或持久化 Refresh Token，只按统一规则验证 Access Token。
- `sub` 使用不可从用户名推导的 Platform User UUID。跨数据库只保存 UUID，不建立跨库外键或共享 ORM。
- Access Token 必须包含身份规范定义的 `iss`、`aud`、`sub`、`role`、`token_type`、`jti`、`iat`、`nbf` 和 `exp`；两个服务使用算法允许列表并分别验证 Audience。

### 禁用与实时授权

- 登录、刷新、创建长期任务、上传、重处理、Internal Retrieval、内部证据原文访问和管理员治理操作必须复核权威用户状态。
- 禁用用户时撤销其全部 Refresh Token Family，并主动失效两个服务的用户状态缓存。
- 知识库权限由 Knowledge Service 根据当前用户、所有权、可见性、资源状态和操作实时计算；Research 传入的角色、owner、visibility 或授权结论均不可信。

### 服务认证

- Internal Retrieval 同时要求 Research 服务身份和终端用户授权上下文，缺一即失败关闭。
- M1 采用带 Key ID、可轮换、短期有效且 Audience 限定为 Knowledge Internal API 的服务 JWT。服务 JWT 使用独立于用户 Token 的签发配置和密钥材料，不携带管理员角色或知识库权限。
- Knowledge 的固定校验顺序为：内部网络边界 → 服务身份 → Contract 版本与请求结构 → 用户启用状态 → 全部目标 KB 当前 READ 权限 → 检索。
- 请求必须传播 `X-Request-ID` 和调用链 ID；认证或授权失败不得进入检索，也不得返回部分 Evidence。

### 敏感数据外发

- 内部文档正文、分块、内部 Evidence 和包含内部信息的用户内容默认禁止发送到外部搜索或模型 Provider。
- `hybrid` 任务分别生成内部检索查询和外部搜索查询；内部结果不得自动拼入外部查询。
- 只有部署策略显式允许目标数据分类、Provider、用途和环境时，才可在最小化、脱敏和审计后外发；任何信息不完整或策略异常均失败关闭。
- 审计记录只保存主体、任务、Provider、用途、策略版本、脱敏摘要、请求关联和允许/拒绝结果，不保存凭证或无必要正文。

### 版本、轮换与失败

- 用户 JWT 和服务 JWT 均支持 Key ID 与双 Key 验证窗口；轮换先发布验证材料，再切换签发，最后在旧 Token 最大有效期后移除旧 Key。
- 缺少或无法加载验证材料时 readiness 失败，不允许退回匿名、管理员身份或不验签模式。
- 删除必需 Claim、改变 `sub`/`role` 语义、改变 Audience 或服务身份语义属于 Breaking Change，必须同步 API、配置、Contract 测试及新的 ADR 检查。

## 后果

- Knowledge 成为身份状态和知识权限的唯一事实源，Research 保持独立数据所有权。
- Internal Retrieval 每次多一次实时状态与权限校验，换取禁用和撤权及时生效。
- 部署需要分别管理用户 JWT 与服务 JWT 的签发/验证材料、Key ID 和轮换窗口。
- M1 必须提供两个服务的共享 Claim Fixture、服务认证负例、权限矩阵和外发泄漏测试，且在 ADR 接受前不得进入验收测试或生产实现。

## 被否决方案

### 两个服务共享用户数据库、ORM 或数据库账号

虽然可以减少一次状态查询，但会破坏 ADR-002 的数据所有权和独立迁移边界，并使 Research 可以绕过 Knowledge 授权。

### 复用用户 JWT 作为服务身份

无法区分浏览器调用与受信服务调用，终端用户可能伪造 Internal Retrieval 调用上下文，也无法独立轮换服务凭证。

### v1.0 直接采用 mTLS 或独立 Identity Service

mTLS 可以提供更强工作负载身份，但会扩大单机 Compose 的证书签发、轮换和运维范围；独立 Identity Service 会新增服务、数据库和故障域。两者保留为部署成熟后的重新评估选项。

### 默认允许私有内容外发，由调用方决定脱敏

调用方实现容易漂移，异常路径可能泄漏内部内容，不满足安全默认开启和失败关闭原则。

## 重新评估触发条件

- 引入独立 Identity Service、企业 SSO、SAML、SCIM 或组织级身份；
- 部署平台具备稳定的工作负载身份或 mTLS 基础设施；
- 服务数量增加，短期服务 JWT 的签发和轮换无法保持最小权限；
- 新 Provider、数据分类或合规要求改变私有内容外发边界；
- 需要改变必需 Claim、Audience、禁用传播或实时授权责任。

## 与既有 ADR 的关系

- 补充 [ADR-002](ADR-002-service-boundary.md) 的跨服务信任与身份载体，不改变其数据所有权和调用方向。
- 补充 [ADR-003](ADR-003-internal-evidence-no-content.md) 的敏感内容处理和实时授权要求，不允许持久化内部正文。
- 不替代现有 accepted ADR；若评审要求改变 ADR-002 或 ADR-003，必须另行创建替代 ADR 并同步状态。

## 相关规范

- [身份与访问](../specs/IDENTITY_AND_ACCESS.md)
- [API 与事件协议](../specs/API.md)
- [总体架构](../specs/ARCHITECTURE.md)
- [配置](../specs/CONFIGURATION.md)
- [测试策略](../specs/TESTING.md)
- [跨服务契约](../../packages/contracts/README.md)
- [Knowledge 数据库](../../services/knowledge/docs/DATABASE.md)
- [Research 数据库](../../services/research/docs/DATABASE.md)
