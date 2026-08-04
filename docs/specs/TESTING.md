# TESTING — 测试与发布验证策略

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 规范基线 |
| 最后更新 | 2026-08-03 |

## 1. 原则

- 测试从权威规格和验收条件导出，不从既有实现反向编写。
- 行为变更先观察目标测试因行为缺失而 RED，再写最小实现进入 GREEN。
- Provider 与 Consumer 共用 Contract Fixture，不复制字段样例。
- 目标阈值与实际结果分离；未运行不得记录 PASS。
- 外部 Provider、时钟、网络和文件系统在边界 Mock，核心权限、状态机和完整度逻辑使用真实代码。

## 2. 环境矩阵

| 环境 | 用途 | 必须验证 |
|:---|:---|:---|
| 单元 | 每次变更 | 纯函数、Service、状态解析、Schema |
| 集成 | 每次候选版本 | API + DB、Worker、Provider/Consumer、SSE |
| Compose | M0 后每次候选版本 | 配置、网络边界、健康、迁移和 smoke |
| 2C2G | M5/M6 | 内存、背压、低并发、恢复和磁盘保护 |
| 恢复环境 | 首次发布和存储变更 | RPO/RTO、备份、恢复、前滚/回滚 |

## 3. 分层测试

### 3.1 架构与静态边界

- 必需目录、独立依赖和独立 Alembic 链；
- Research 无 Knowledge DB、Chroma、上传卷或 `app` import；
- Nginx 不暴露 `/internal/v1`、`/metrics` 和数据服务；
- Redis Key、队列和 Metric 带服务命名空间；
- 文档相对链接、OpenAPI、JSON Schema 和 `$ref` 可解析。

### 3.2 身份与权限

- IA-001：Knowledge 签发的 Access Token 使用 Platform User UUID 作为 `sub`，包含完整必需 Claims；Knowledge 与 Research 分别验证自身 Audience 后识别出相同 UUID 与角色；
- IA-002：两个服务拒绝错误算法、Issuer、Audience、`token_type`、非法 UUID、缺失必需 Claim、尚未生效和已过期的 Access Token，且只返回统一安全认证错误；
- IA-001-B：Research 不注册任何 `/api/auth/*` 身份写接口，其 ORM Metadata 不包含 `users` 或 `refresh_tokens`；Research 只验证 Knowledge 签发的 Access Token；
- IA-003/IA-011：登录创建以 Platform User UUID 归属的 Refresh Token Family；刷新使用行锁原子标记旧 Token、记录唯一后继并签发新 Token，同一旧 Token 至多产生一个有效后继；
- IA-004：重放已轮换 Refresh Token 时撤销整个 Family、持久化携带 `request_id` 且不含 Token 的安全事件，并返回 `E5009`；普通撤销 Token 不得误判为重放；
- IA-012 基线：Knowledge Internal API 拒绝缺失、伪造、过期、错误 Issuer/Audience/类型/Key ID 的 Service JWT；拒绝缺失或非法的 Platform User UUID、Contract 版本、`X-Request-ID` 和 `traceparent`，且不得进入用户查询或后续检索；
- IA-010 密钥轮换：Service JWT 双 Key 验证窗口内新旧 Token 均按 Key ID 通过，窗口后移除旧 Key 后旧 Token 失效、新 Token 仍有效；切换签发侧使用新 Key ID 签发后按新 Key 验证通过（`test_service_security.py::TestServiceKeyRotation`）；
- IA-012 身份状态 Contract：active 用户只返回 Platform User UUID、`status=active` 和非负 `status_version`；用户不存在或禁用统一返回 `AUTH_USER_DISABLED`；身份库不可用返回可重试的 `INTERNAL_IDENTITY_UNAVAILABLE`，Research 创建任务失败关闭且不分发 Worker；
- IA-013 Access Token 不含 `username` 等可派生展示字段；`username`/`role`/`status` 显示信息必须由 `/api/v1/auth/me` 从数据库当前状态读取，不得从 Token Claim 拼装；
- IA-014 `/api/v1/auth/me` 直接返回 `UserSummary`（`id` 为合法 UUID 字符串，来自 `users.platform_user_id`）；Token 无效返回 `401 E5004`，用户不存在或禁用统一返回 `401 E5010`；
- IA-015 Refresh Cookie/CSRF：登录设置 HttpOnly Refresh Cookie 与非 HttpOnly CSRF Cookie，响应体不含 Refresh Token；刷新和退出必须携带匹配的 `X-CSRF-Token`，缺失、不一致或 Origin 不允许时返回认证错误，且不得解码、轮换、撤销 Token Family 或写入重放审计；刷新成功同时轮换 Refresh Cookie 与 CSRF Cookie；
- IA-016 迁移期兼容：配置允许时旧 JSON Body `refresh_token` 可完成刷新/退出并记录不含 Token 的弃用用量；配置关闭时 body `refresh_token` 被拒绝。Web 新代码不得读写 `localStorage.refresh_token`，刷新和退出只依赖 Cookie 与 CSRF Header；
- IA-017 外部 User DTO 与遗留接口退出：`/api/v1/auth/register` 和 `/api/v1/auth/me` 返回的 User DTO `id` 均为 Platform User UUID，响应不得包含 Knowledge 内部 `users.id`；旧 `/api/auth/*` 和旧 `id=int` UserResponse 只在配置允许的迁移期可用，必须有调用量观测，关闭后 Web、脚本和 API 测试全部使用 `/api/v1/auth/*`；
- 退出撤销当前 Refresh Token Family；
- 禁用用户不能登录、刷新、创建任务、Chat、上传、重处理、治理写操作或 Internal Retrieval；
- 知识库权限矩阵（PRD §8.2）：READ 由 visibility 优先（public→所有登录用户，private→owner+admin），WRITE 由 ownership 决定且 admin 治理覆盖（owner+admin），上传文档 owner-only（admin 作为非 owner 不可代传）；纯函数矩阵测试覆盖 `test_permissions.py::TestRequireKbReadable/TestRequireKbWritable/TestRequireKbOwner`；
- Internal Retrieval 任一 KB 无权时整批失败且检索未执行；
- 历史报告展开内部来源时实时复核权限；
- M1 退出门禁 6：登录成功与失败路径日志均不得包含密码或 Access/Refresh Token 明文（`test_auth_service.py::TestLoginLogSensitivity`）；生产模式错误响应屏蔽内部堆栈与异常细节（`test_error_handlers.py`）。

### 3.3 Knowledge

- 文档入库、重处理、失败清理、删除和恢复；
- 单 KB Chat、会话绑定、取消和来源定位；
- Vector/BM25/RRF/粗排/Rerank/Evidence Review 降级；
- 多 KB Internal Retrieval 的逐 KB 鉴权、公平合并和内存上限；
- Chat SSE 顺序、唯一终态和半截消息防护。

### 3.4 Research

- 七阶段顺序和 `fetching=skipped`；
- `knowledge|web|hybrid` 来源隔离；
- Task/Step 状态、租约 generation、取消竞态和恢复；
- Internal excerpt 禁入所有持久对象和事件；
- Evidence Relation、冲突披露和完整度纯函数；
- Report Revision 原子发布与不可变性；
- Research SSE 重连、重复事件幂等和快照恢复。

### 3.5 Web

- v1.0 Chat 选择器单选；多选不可执行并显示规划提示；
- Research 多 KB 选择、来源策略和数据使用说明；
- Chat/Research 两套 SSE 解析器；
- 引用与 Evidence 双向定位；
- 权限撤销后清理内部正文；
- 键盘、焦点、对比度和 reduced motion。

## 4. Contract 门禁

Internal Contract 每个版本必须通过 Meta-Schema、唯一 `$id`、可解析 `$ref`、有效/无效 Fixture、生成物无差异、Knowledge Provider 和 Research Consumer 测试。External OpenAPI 必须通过语法、引用、示例和 Breaking Change 检查。

契约 Schema 与 Fixture 以 `packages/contracts/` 为唯一权威源，双方测试不得复制 Schema 或自造 Fixture。已落地的 Internal Identity Status 契约测试分布：

- Schema 自检：`packages/contracts/tests/`（Meta-Schema、`$id` 唯一、`$ref` 可解析、Fixture 校验）；
- Knowledge Provider：`services/knowledge/tests/contract/`（端点 `GET /internal/v1/identity/users/{id}/status` GREEN，9 个测试覆盖有效/无效/禁用/缺失/信封场景）；
- Research Consumer：`services/research/tests/contract/`（只消费/拒绝 Fixture，独立运行，不依赖端点）；
- Research 身份状态门禁 GREEN：`services/research/tests/unit/core/test_identity_status_client.py`（200→放行、403→`UserDisabledException`、503/网络/超时→`ServiceUnavailableException`，校验 Service JWT/Contract 版本/`X-Request-ID`/`traceparent` 请求头）与 `tests/unit/services/test_research_service.py::TestCreateTaskIdentityGate`、`tests/unit/api/test_research.py::TestCreateResearchIntentAPI`（禁用用户/身份库不可用 → 创建失败关闭，无任务行、不分发 Worker）。

运行命令：

```bash
python3 -m pytest packages/contracts/tests
cd services/knowledge && python -m pytest tests/contract   # 或在 knowledge 容器内执行
cd services/research && python -m pytest tests/contract
```

`jsonschema==4.*` 是契约测试的测试依赖，已登记在 `requirements-dev.txt`、`services/knowledge/requirements.txt` 与 `services/research/requirements.txt`。

## 5. PRD 验收映射

| 指标 | 验证入口 |
|:---|:---|
| AC-001 | Claim—Evidence 关系自动检查 + 试点评审 |
| AC-002 | 权限矩阵、安全审查和来源二次鉴权 |
| AC-003 | 冻结评估集的 Research Task 统计 |
| AC-004 | Worker 中断和租约恢复演练 |
| AC-005 | 固定文档集入库统计 |
| AC-006 | 固定 Knowledge 评估集 Recall@5 |
| AC-007 | 候选版本全量回归 |
| AC-008 | 同题人工与 EvidSight 对照 |
| AC-009 | 统一五级问卷和回访 |
| AC-010 | 报告 Evidence 自动检查 |

实际结果必须记录评估集版本、提交、镜像、日期、资源、命令、样本数和失败明细。

## 6. Monorepo 基线验证命令

```bash
python3.12 -m pytest tests/architecture -v
uv run --project services/knowledge pytest
uv run --project services/research pytest
npm --prefix apps/web test
npm --prefix apps/web run build
docker compose config --quiet
```

命令必须在当前候选提交上实际执行；失败、跳过或环境缺失均不得记为通过。

## 7. 发布记录模板

```text
候选版本/提交：
环境与资源：
数据集版本：
执行命令：
通过/失败/跳过：
已知偏差与批准人：
证据链接：
```

原 `docs/migration/` 过程记录已由负责人于 2026-08-02 主动删除，不再作为 M0 或 M1 门禁。后续候选版本的实际验证结果应使用本节模板记录在对应评审或发布记录中；M6 发布验收必须单独建立带日期的候选版本记录。
