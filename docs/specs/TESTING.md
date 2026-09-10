# TESTING — 测试与发布验证规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 规范基线 |
| 最后更新 | 2026-08-09 |

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
| 开发单机 Compose | 每次候选版本 | Mac 可离线启动完整栈、配置、网络边界、健康、迁移和 smoke |
| 生产三节点 Compose | M5/M6 | 三台 2C2G 节点落位、私网、资源、背压、故障语义和节点联合 smoke |
| 恢复环境 | 首次发布和存储变更 | 跨节点同批次 RPO/RTO、备份、恢复、前滚/回滚 |

### 2.1 自动化门禁分层

自动化按风险和运行环境分为三层，后一层增加验收深度，不取代前一层：

| 层级 | 阶段与触发 | 必须覆盖 | 明确不覆盖 |
|:---|:---|:---|:---|
| 基础 CI | 当前开发阶段；受保护分支的 PR 和推送 | Python/Web 静态门禁、不依赖外部服务的快速单元测试、Contract、Architecture、开发 Compose 配置解析、External OpenAPI 检查 | 真实 MySQL/Redis/Celery/Chroma 全栈回归、真实外部 Provider、评估集、生产三节点、镜像发布和故障/恢复演练 |
| 部署与集成验收 | M5；候选构建或明确的手工验收 | Docker 镜像构建与缓存、单机 Compose 全栈集成、迁移往返、Worker/SSE、跨服务 Provider/Consumer、镜像安全、三节点静态与 staging、备份/恢复/回滚/故障演练 | 不代表 v1.0 已通过发布决策 |
| 候选版本发布门禁 | M6；冻结候选版本 | M0—M5 全部证据、AC-001—AC-010、端到端场景、安全/容量/恢复/回滚复核、不可变构建标识、候选版本报告和制品发布 | 不接收未完成的大型架构改造 |

基础 CI 只读检查当前提交，不执行格式化、生成后回写、自动提交或推送。本地 commit 由 pre-commit 拦截；远端 CI 作为受保护分支的 required checks，通过才允许合并，不将“已创建 commit”表述为“CI 已通过”。所有依赖使用版本化锁文件冻结安装；缓存只影响速度，不得成为正确性前提。

基础 CI 的后端快速单元测试必须使用稳定 marker 或显式清单选择，覆盖本次变更受影响的纯函数、Service、Schema 和状态解析；不得用模糊的路径排除或“总数少于某值”代替用例分类。该层的墙钟时间目标为 5–10 分钟；只有连续运行记录支持时才能宣称达标，超时时先通过并行与安全缓存优化，不得静默删除必过门禁。

## 3. 分层测试

### 3.1 架构与静态边界

- 必需目录、独立依赖和独立 Alembic 链；
- Research 无 Knowledge DB、Chroma、上传卷或 `app` import；
- Nginx 不暴露 `/internal/v1`、`/metrics` 和数据服务；
- 三份生产 Compose 的组件全集无缺失，Knowledge/Research Beat 各只有一个，外部端口只存在于云节点 1；
- Knowledge API、Worker、Beat、uploads 与 Chroma 同属云节点 3，Research 不挂载 Knowledge 卷；
- Mac/Windows 不出现在生产核心依赖或 readiness 中；
- Redis Key、队列和 Metric 带服务命名空间；
- 文档相对链接、OpenAPI、JSON Schema 和 `$ref` 可解析；
- Python 代码通过 ruff 静态检查（规则集 `E4,E7,E9,F,I`，行宽 100，配置见根 `pyproject.toml`）；lint 只报告，不改文件。提交时由 pre-commit hook（`.pre-commit-config.yaml`，`repo: local` 调用 venv 内 ruff）对暂存文件自动执行 `ruff check` 与 `ruff format --check`，存量基线告警按「触碰即清理」增量消解；提交信息由 `commit-msg` hook（`scripts/check_commit_msg.sh`）强制 `add|fixed|update|refactor: 中文描述` 格式。
- Python 类型检查采用 mypy 全量门禁。六批收口后的最终强制范围为：① Knowledge/Research 两服务完整 `app/`（包括 Schema、Core、API、Service、Pipeline/Task/Worker、基础设施与外部 Provider 客户端、ORM、Evaluation、Metrics、Utils 和入口）；② 两服务 `scripts/`（不含 `.ab/` 临时噪声实验目录）、`tests/` 与 `alembic/env.py`；③ 根 `tests/`；④ `packages/contracts/generated/python/` 与 `packages/contracts/tests/`。Alembic 历史 revision 属生成且已落库的迁移事实，继续由迁移往返验证，不纳入 mypy；缓存、venv 与其他生成目录继续排除。两服务及共享范围必须使用同一根配置分别检查，全部结果为零错误；日常检查与 pre-commit 使用 `make setup-python-dev` 建立的各服务 Python 3.12 `.venv`，检查过程不得临时安装依赖；候选版及 Python requirements/Dockerfile 变化必须再执行 `make type-check-docker`，使用 Dockerfile 缓存的 `typecheck` target 在 Linux Python 3.12 中复核，运行容器不得联网安装依赖。启用 Pydantic mypy plugin、`check_untyped_defs`、严格 Optional、冗余 cast 与无效 ignore 检查；不得用全局 `ignore_missing_imports`、全局 `ignore_errors` 或批量 `# type: ignore` 伪造通过。新增 Python 文件必须在所属环境的全量门禁中立即清零，不再保留后续批次豁免。
- Mac 上仅编辑器解析、ruff、mypy、pre-commit 与不依赖外部服务的纯单元检查可使用服务 `.venv`；API+DB、迁移、Worker/Celery、Redis、跨服务 Provider/Consumer、SSE、smoke 及完整回归必须使用根 Docker Compose 环境。不连接数据服务、不发起跨服务请求的隔离 Provider 契约测试可按 §4 使用对应服务的受管容器单独执行。不得为绕过容器依赖缺失而在一次性运行容器中 `pip install`，开发/测试依赖必须进入版本化 requirements 与可缓存构建 target。
- Web 只保留 `pnpm-lock.yaml`，冻结安装、ESLint、Prettier 检查、TypeScript 类型检查、Vitest 与 Vite 构建均通过；前端相关暂存文件由 pre-commit 调用 `lint` 与 `format:check`，hook 只报告、不修改文件。具体工具边界与验收条件以 [FRONTEND.md §2.2](../../apps/web/docs/FRONTEND.md#22-工程工具链) 为准。
- Web Design Token 静态门禁必须验证：所有 `--es-*` 引用在 `tokens.css` 中声明、业务源码不存在颜色字面量、生产代码不消费跟踪版原型旧 Token、Tailwind 映射不创建第二套视觉事实；任一项失败阻止切片完成。
- 跟踪版交互原型 manifest 必须可解析，20 个页面 ID 唯一，交互源和 light/dark PNG 均存在，PNG 宽度为 1280px 且高度不低于 720px；参考目录不得包含 `package.json` 或进入生产构建，防止形成第二前端。

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
- 每个页面切片在实现前建立同状态视觉 RED，并在完成前通过固定 Chromium、1280×720、device scale 1、本地字体和确定性 Fixture 的 Playwright 截图回归；页面视觉回归不得推迟到最终 E2E 切片。
- 入口/登录、AppShell/工作台、知识中心、Chat、Research、Report/Evidence 和 Admin 分别拥有自己的视觉用例；切片 8 只补跨页面业务旅程。
- 自动截图差异阈值必须在首次基线评审时统一固定，后续阈值变化属于验收标准变更，必须先完成文档裁决，不得为单次失败临时放宽。

### 3.6 部署拓扑与故障演练

- 根 `docker-compose.yml` 在不连接生产私网的 Mac 上启动完整开发栈，且只使用开发卷、开发密钥和 Compose 服务发现；
- `deploy/compose/cloud-edge.yml` 只包含 Edge/Research 组件，`cloud-data.yml` 只包含 MySQL/Redis/备份组件，`cloud-knowledge.yml` 只包含完整 Knowledge 数据岛；
- 三份生产 Compose 独立通过配置解析，联合检查组件实例数、队列、卷、Secret 和端口边界；
- 公网探测只能访问云节点 1 的 `80/443`，MySQL、Redis、Knowledge API、Internal API 与 metrics 公网不可达；
- 私网 DNS 解析失败、时间偏差超限或节点间连接中断时 readiness 失败，不回退公网地址或放宽鉴权；
- 云节点 1、2、3 分别中断时符合 ADR-011 故障语义，恢复后不会重复 Beat、重复提交 Step 或绕过当前权限；
- Mac/Windows 中断时生产核心 API、Worker、数据库和 Broker 不受影响；
- 生产允许 Knowledge 与 Research 各执行一个重任务；开发单机模式通过跨服务重任务准入锁避免 OOM；
- MySQL 与 uploads/Chroma 使用同一 `backup_batch_id` 完成空环境恢复，实际 `RPO ≤ 24h`、`RTO ≤ 4h`。

## 4. Contract 门禁

Internal Contract 每个版本必须通过 Meta-Schema、唯一 `$id`、可解析 `$ref`、有效/无效 Fixture、生成物无差异、Knowledge Provider 和 Research Consumer 测试。External OpenAPI 必须通过语法、引用、示例和 Breaking Change 检查。

基础 CI 对 Contract 变更执行 `packages/contracts/README.md` 定义的全部当前可执行门禁。生成物差异检查只对已登记且可重复执行的生成 target 生效；当前 Python/Pydantic 参考生成物虽已入库，但可重复生成命令尚未登记，TypeScript 生成链亦未落地，两者都不得被记为“重新生成后无差异”已通过。新增或补齐生成 target 必须在同一变更中纳入差异检查，从登记之时起成为 Contract 变更的必过项。

Knowledge Provider 契约测试即使使用 FakeSession 或 Mock 隔离数据服务，仍按 Provider/API 测试管理，必须在受管的服务容器环境执行；只有 Schema、Fixture、纯生成物检查与不导入服务 `app` 的 Consumer 测试可在固定开发环境中执行。这一约束不要求基础 CI 启动 MySQL、Redis、Celery 或 Chroma，但容器内测试必须在依赖未连接时仍可确定性执行。

External OpenAPI 基础 CI 必须校验：OpenAPI 版本与文档语法、所有本地及跨文件 `$ref`、Schema 与操作示例、FastAPI 路由的 method/path 双向一致性、Provider 契约测试覆盖登记，以及相对受保护基线的 Breaking Change。路由一致性必须分别提取 Knowledge 与 Research 两个 FastAPI App 的全部浏览器外部 `/api/v1/*` 操作并汇总双向比对；不得通过前缀白名单只检查当前切片、不得把内部 API、legacy 路由或仅有实现测试的端点记为 External OpenAPI 已覆盖。Chat/Research SSE 除路径外还必须逐事件校验事件名、顺序与每种 `data` Schema。首个受保护 OpenAPI 基线只执行前五项；基线合并后，Breaking Change 检查立即成为必过项。仅检查 `openapi`/`info`/`paths`/`components` 键存在不算语法或 `$ref` 验证通过。

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
| AC-001 | Claim—Evidence 关系自动检查 + 试点评审（Research 入口 `services/research/scripts/verify_ac001_claim_evidence.py`，门槛 ≥ 90%） |
| AC-002 | 权限矩阵、安全审查和来源二次鉴权 |
| AC-003 | 冻结评估集的 Research Task 统计（`services/research/scripts/verify_ac003_task_success.py`，门槛 ≥ 95%，排除用户主动取消） |
| AC-004 | Worker 中断和租约恢复演练（`services/research/scripts/verify_ac004_recovery_drill.py`，门槛 ≥ 95%） |
| AC-005 | 固定文档集入库统计 |
| AC-006 | 固定 Knowledge 评估集 Recall@5 |
| AC-007 | 候选版本全量回归 |
| AC-008 | 同题人工与 EvidSight 对照 |
| AC-009 | 统一五级问卷和回访 |
| AC-010 | 报告 Evidence 自动检查（Research 入口 `services/research/scripts/verify_ac010_traceability.py`，门槛 100%；Knowledge 入口 `services/knowledge/scripts/verify_ac010_traceability.py`） |

实际结果必须记录评估集版本、提交、镜像、日期、资源、命令、样本数和失败明细。

## 6. 执行与证据要求

- 验证命令、环境准备和发布记录格式由 [测试执行指南](../guides/TEST_EXECUTION.md) 维护，不在规范中复制操作步骤；
- 命令必须在当前候选提交和登记环境上实际执行；失败、跳过或环境缺失均不得记为通过；
- 三份生产 Compose 的单独配置解析不能替代联合静态检查、实际私网暴露检查、节点中断演练和跨节点恢复演练；
- 实际结果必须记录候选版本、环境资源、数据集、命令、通过/失败/跳过、已知偏差、批准人和证据链接；
- M6 发布验收必须建立带日期的独立候选版本记录。

ADR 检查 1–8：否。本文将既有测试与发布要求分层为基础 CI、M5 部署/集成验收与 M6 候选发布门禁，不改变服务边界、公共契约、数据、安全或生产运行机制。
