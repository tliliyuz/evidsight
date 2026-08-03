# ADR-006：Refresh Token 浏览器传输（HttpOnly Cookie + double-submit CSRF）

- 状态：accepted
- 日期：2026-08-03
- 里程碑：M1
- 命中的 ADR 检查项：3、4、7

## 背景

当前浏览器认证实现（`apps/web/src/api/index.js`）与权威规范冲突：Refresh Token 明文写入 `localStorage`，刷新使用 body `{ refresh_token }` 且无 CSRF 校验，无 `withCredentials`，无 `X-CSRF-Token` Header。这与 `IDENTITY_AND_ACCESS.md` §4.2「Refresh Token 禁止进入 Local Storage、浏览器目标态必须使用 HttpOnly Cookie + CSRF」及 `FRONTEND.md` §5.1.2 冲突。

ADR-005 只裁决了统一身份、服务认证与数据外发，未裁决浏览器 Refresh Token 传输载体。本决策把浏览器传输收口到 Cookie + CSRF，属于对外部认证 API、浏览器安全边界和部署/跨域配置的长期约束，因此命中 ADR 检查 3（公共契约）、4（数据与安全）、7（跨规范影响）。

## 决策

### 浏览器目标态

- Refresh Token 由 Knowledge Auth API 通过 **HttpOnly Refresh Cookie** 设置、轮换和清除，禁止进入 URL、SSE、Analytics、普通应用日志、Local Storage、Session Storage、IndexedDB、可读 Cookie 或前端业务状态。
- Refresh Cookie 名称由配置定义，生产环境必须使用 `__Host-` 前缀、`Path=/`、`HttpOnly`、`Secure`、`SameSite=Lax`；跨站部署需要 `SameSite=None; Secure` 时，必须同时启用严格 Origin 校验。`Path=/` 是 `__Host-` 前缀的强制要求（RFC 6265bis §5.5：`__Host-` Cookie 必须 `Secure` + `Path=/` + 无 `Domain`）；Cookie 仍只被 `/api/v1/auth/refresh` 与 `/api/v1/auth/logout` 作为凭据读取，其他业务接口不得将其作为认证凭据。（2026-08-03 文档裁决方案 A 更正 Path）
- Access Token 仍在响应体返回，由前端保存在内存或受控短期状态中并通过 `Authorization: Bearer` 调用业务 API；不得写入长期可读持久存储。
- Cookie 只用于 `/api/v1/auth/refresh` 与 `/api/v1/auth/logout`，不得被其他业务接口作为认证凭据。

### CSRF 防护

- 采用 **double-submit 模式**：Knowledge Auth API 同时设置一个非 `HttpOnly` 的 CSRF Cookie，前端在刷新和退出请求中回传同值 `X-CSRF-Token` Header。
- 服务端必须在执行任何 Refresh Token 解码、哈希查询、轮换或撤销前完成 CSRF 校验；Header 缺失、Cookie 缺失、值不一致或 Origin 不在允许列表时返回安全认证错误，且不得改变 Token Family 或写入重放审计。
- 登录成功创建 Token Family 后设置 Refresh Cookie 与 CSRF Cookie；刷新成功必须在同一响应中轮换 Refresh Cookie 与 CSRF Cookie；退出、重放检测、Token Family 撤销和用户禁用后的刷新失败必须清除 Refresh Cookie。

### 登录、刷新与退出

- **登录**：设置 Refresh Cookie 与 CSRF Cookie，返回 Access Token 和最小用户摘要；响应体不得包含 Refresh Token 明文。
- **刷新**：先校验 CSRF 与 Origin；从 Refresh Cookie 读取 Token，迁移期可在配置允许时回退读取 JSON Body；原子轮换，同一旧 Token 至多产生一个有效后继；并发刷新只允许一个请求成功。
- **退出**：幂等。先校验 CSRF 与 Origin；撤销当前 Token Family，清除 Refresh Cookie 与 CSRF Cookie；重复退出不得泄露 Token 是否曾有效。

### 迁移期兼容

- `EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT` 配置开启时，允许后端继续接受 JSON Body 中的 `refresh_token`，仅作为旧 Web 调用兼容入口，记录不含 Token 的弃用调用量。
- 兼容入口在观测窗口归零、Web 与脚本 Consumer 全部切换到 `/api/v1/auth/*` 且回归测试通过后删除；前端目标态不得再读取、写入或传递 Body refresh_token。
- 若部署明确选择响应体模式作为长期例外，必须在本决策关联规范中重新完成 ADR 检查并记录 XSS 风险、退出清理和禁用传播影响。

## 后果

- 前端认证协议整体切换为 Cookie + CSRF；`localStorage.refresh_token` 逐步下线并最终移除。
- 部署要求：生产必须配置严格 Origin 白名单与 `Secure` Cookie；跨站部署需 `SameSite=None` + Origin 校验。
- 外部认证 API 响应契约变化：`login`/`refresh` 不再返回 `refresh_token` 明文，`refresh`/`logout` 新增必需 `X-CSRF-Token` Header。
- 迁移期 `body refresh_token` 兼容入口在观测窗口归零后删除。

## 被否决方案

### 维持响应体返回 Refresh Token + 前端受控存储

Refresh Token 继续放响应体，前端存入内存/受控存储（非 localStorage）。实现改动最小，但 XSS 仍可窃取内存中的 Token，无 CSRF 边界，且与已固化的权威文档目标态冲突。

### 独立 CSRF 端点下发 + 服务端绑定

服务端签发 CSRF Token 并绑定 Session/DB，前端从独立端点获取。新增状态存储与端到端依赖，增加 API 面与状态管理；double-submit 已满足威胁模型，复杂度不必要。

## 重新评估触发条件

- 引入独立 Identity Service、企业 SSO、SAML、SCIM 或组织级身份；
- 部署平台提供更强的浏览器凭据基础设施（如 WebAuthn、FedCM）或工作负载身份；
- 跨站部署规模扩大，`SameSite`/Origin 校验需要更细粒度的信任模型；
- 需要改变必需 Cookie 属性、CSRF 模式或兼容入口退出窗口。

## 与既有 ADR 的关系

- 补充 [ADR-005](ADR-005-unified-identity-service-auth-egress.md)：ADR-005 裁决统一身份、服务认证与数据外发，本 ADR 落实其浏览器端 Refresh Token 传输安全收口；不改变身份事实源、服务边界、Token Family 语义或跨服务信任方向。
- 不改变 [ADR-002](ADR-002-service-boundary.md)、[ADR-003](ADR-003-internal-evidence-no-content.md)。
- 涉及 [ADR-004](ADR-004-web-framework-transition.md) 演进路径内的前端实现。

## 相关规范

- [身份与访问](../specs/IDENTITY_AND_ACCESS.md) §4.2 / §5
- [API 与事件协议](../specs/API.md) §5
- [配置](../specs/CONFIGURATION.md) §3.1
- [前端文档](../../apps/web/docs/FRONTEND.md) §5.1.2
- [测试策略](../specs/TESTING.md) IA-015 / IA-016
