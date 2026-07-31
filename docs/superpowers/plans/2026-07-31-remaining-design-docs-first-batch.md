# EvidSight 剩余设计文档第一批实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对齐 EvidSight 专项规范目录，并完成统一身份与权限设计及 API 协议基线，使后续 Contract、数据库、Pipeline 和前端规范拥有稳定输入。

**Architecture:** PRD 保持产品真理源，ARCHITECTURE 保持系统边界真理源；新建 `IDENTITY_AND_ACCESS.md` 管理身份、授权和敏感数据外发，新建 `API.md` 管理 HTTP、错误与 SSE。跨服务字段 Schema 留给 `packages/contracts/`，数据库和 Pipeline 内部实现继续由各服务专项文档负责。

**Tech Stack:** Markdown、Git、Python 3.12 标准库文档检查脚本（命令内联执行，不新增依赖）

## Global Constraints

- 本计划只修改规范文档，不创建生产代码、数据库迁移或运行时配置。
- 不改变 `docs/PRD.md` 已确认的产品范围和权限矩阵。
- 不改变 `docs/ARCHITECTURE.md` 已确认的服务所有权、网络边界和数据隔离原则。
- 新正式外部协议使用 `/api/v1/*`；Internal Retrieval 使用 `/internal/v1/retrieval/*`。
- Chat SSE 与 Research SSE 只共享帧级规则，不共享业务事件状态机。
- 服务凭证只认证调用服务，不能替代终端用户授权。
- Knowledge Service 必须实时重新计算用户对目标知识库的 READ 权限。
- 同一种技术事实只在一个权威文档中定义，其他文档使用交叉引用。
- 不覆盖或恢复开始本计划前已有的未提交修改和删除状态。
- 纯文档变更使用链接、格式、术语和跨文档一致性检查作为验证证据。

---

## 文件结构

| 文件 | 操作 | 单一职责 |
|:---|:---|:---|
| `docs/PRD.md` | 修改 §14 | 列出产品相关专项文档，不承载技术细节 |
| `docs/ARCHITECTURE.md` | 修改 §17 | 声明后续专项边界及不得突破的架构约束 |
| `docs/ROADMAP.md` | 修改 §4、§7 | 给出完整、可执行的文档依赖顺序 |
| `docs/IDENTITY_AND_ACCESS.md` | 新建 | 身份、令牌、授权上下文、服务认证和敏感数据外发的权威规范 |
| `docs/API.md` | 新建 | 路由、HTTP、错误、并发、幂等、SSE 和兼容策略的权威规范 |

---

### Task 1：对齐专项文档目录与权威边界

**Files:**
- Modify: `docs/PRD.md:611`
- Modify: `docs/ARCHITECTURE.md:541`
- Modify: `docs/ROADMAP.md:455`
- Modify: `docs/ROADMAP.md:505`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-31-remaining-design-docs-first-batch-design.md` §3、§4.1、§9。
- Produces: 后续任务引用的完整文件清单、唯一权威边界和依赖顺序。

- [ ] **Step 1：记录修改前目录不一致的 RED 证据**

运行：

```bash
python3.12 - <<'PY'
from pathlib import Path

required = {
    "docs/IDENTITY_AND_ACCESS.md",
    "docs/API.md",
    "packages/contracts/",
    "services/knowledge/docs/DATABASE.md",
    "services/knowledge/docs/RAG_PIPELINE.md",
    "services/research/docs/DATABASE.md",
    "services/research/docs/RESEARCH_PIPELINE.md",
    "apps/web/docs/FRONTEND.md",
    "apps/web/docs/UIDESIGN.md",
    "docs/DATA_MIGRATION_AND_ROLLBACK.md",
    "docs/TESTING.md",
    "docs/CHANGELOG.md",
    "docs/decisions/",
}
for name in ("docs/PRD.md", "docs/ARCHITECTURE.md", "docs/ROADMAP.md"):
    text = Path(name).read_text()
    missing = sorted(item for item in required if item not in text)
    print(f"{name}: missing={missing}")
    assert not missing
PY
```

预期结果：失败，并分别打印 PRD、ARCHITECTURE、ROADMAP 缺失的专项文档路径。

- [ ] **Step 2：更新 PRD §14 的相关文档清单**

保留已有三份已完成文档链接，并按以下类别补齐：

1. 身份与接口：`IDENTITY_AND_ACCESS.md`、`API.md`、`packages/contracts/`；
2. 服务内部：两个 `DATABASE.md` 和两个 Pipeline 文档；
3. 用户体验：`FRONTEND.md`、`UIDESIGN.md`；
4. 交付治理：`DATA_MIGRATION_AND_ROLLBACK.md`、`TESTING.md`、`CHANGELOG.md`、`decisions/`。

每项标记“待编写”或“待设计”，但不复制字段、算法或实现要求。将 PRD 文档版本增加一个补丁版本，并保持产品阶段不变。

- [ ] **Step 3：更新 ARCHITECTURE §17 的专项设计边界**

将现有六类边界改为带精确文件路径的依赖序列：

1. `MONOREPO_MIGRATION_PLAN.md`；
2. `IDENTITY_AND_ACCESS.md`；
3. `API.md` 与 `packages/contracts/`；
4. Knowledge Database/Pipeline；
5. Research Database/Pipeline；
6. Frontend/UI Design；
7. `DATA_MIGRATION_AND_ROLLBACK.md`；
8. `TESTING.md`；
9. `CHANGELOG.md` 与 `decisions/`。

保留“不得改变服务所有权、网络边界和数据隔离，确需改变先更新架构并新增 ADR”的约束。

- [ ] **Step 4：更新 ROADMAP §4 和 §7**

在 §4 使用与 ARCHITECTURE §17 相同的九步顺序，并明确：

- Identity 文档先于字段级 API；
- API 先定义协议表面，Contract 再固化跨服务 Schema；
- 两个服务的 Database/Pipeline 在 Contract 之后；
- Frontend/UI 在稳定 API、SSE 和 Evidence Contract 之后；
- 数据迁移和测试策略在发布门禁前完成；
- CHANGELOG/ADR 全程维护，不是最后一次性补写。

同步更新 §7 链接，不保留已知失效路径。

- [ ] **Step 5：运行目录一致性检查并确认 GREEN**

重新运行 Step 1 命令。

预期结果：退出码 `0`，三个文件均输出 `missing=[]`。

- [ ] **Step 6：检查 Task 1 差异**

运行：

```bash
git diff --check -- docs/PRD.md docs/ARCHITECTURE.md docs/ROADMAP.md
git diff -- docs/PRD.md docs/ARCHITECTURE.md docs/ROADMAP.md
```

预期结果：`git diff --check` 无输出；差异只涉及文档元数据、§14、§17、§4 和 §7，不改动产品功能或架构事实。

- [ ] **Step 7：提交目录对齐变更**

```bash
git add docs/PRD.md docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "docs: align EvidSight design document inventory"
```

---

### Task 2：编写统一身份与权限设计

**Files:**
- Create: `docs/IDENTITY_AND_ACCESS.md`

**Interfaces:**
- Consumes: PRD §7.1、§8、§11.2、§13；ARCHITECTURE §4、§7.1、§8.1、§9、§10；Task 1 的权威边界。
- Produces: API 文档可引用的 JWT、刷新、禁用、服务凭证、授权上下文和数据外发语义。

- [ ] **Step 1：创建身份规范验收检查并确认 RED**

运行：

```bash
python3.12 - <<'PY'
from pathlib import Path

path = Path("docs/IDENTITY_AND_ACCESS.md")
assert path.exists(), "IDENTITY_AND_ACCESS.md does not exist"
text = path.read_text()
required = [
    "## 1. 目标与边界",
    "## 2. 身份主体与信任关系",
    "## 3. Access Token",
    "## 4. Refresh Token",
    "## 5. 登录、刷新与退出",
    "## 6. 用户禁用语义",
    "## 7. 服务间认证与用户授权上下文",
    "## 8. 资源授权规则",
    "## 9. 内部证据实时复核",
    "## 10. 敏感数据外发策略",
    "## 11. 审计与可观察性",
    "## 12. 密钥轮换、兼容与失败",
    "## 13. 验收场景",
]
missing = [heading for heading in required if heading not in text]
assert not missing, missing
PY
```

预期结果：失败，提示文件不存在。

- [ ] **Step 2：写入文档头、目标、主体与信任关系**

文档头标记 `v1.0`、`已确认设计`、日期 `2026-07-31`，并明确：

- Knowledge Service 身份模块签发令牌并拥有 `platform_db` 身份数据；
- Research Service 只验证 Access Token，不签发或保存 Refresh Token；
- 浏览器、Knowledge、Research、管理员和外部 Provider 是不同信任主体；
- Platform User ID 是跨服务稳定用户标识；
- `user` 与 `admin` 是 v1.0 唯一系统角色。

- [ ] **Step 3：定义 Access Token 契约**

明确必需 Claims：`iss`、`aud`、`sub`、`role`、`token_type=access`、`jti`、`iat`、`nbf`、`exp`；时间为 UTC NumericDate。定义：

- `sub` 是 Platform User ID，不使用用户名或数据库自增 ID；
- `aud` 必须允许两个服务显式验证，禁止跳过 Audience；
- 算法从配置读取并使用允许列表，禁止接受令牌头任意算法；
- 两个服务共享验证语义，但密钥通过部署 Secret 提供；
- 默认短时有效，精确默认值归配置 Schema，文档只规定上下限与变更兼容要求；
- 每次受保护请求同时验证签名、算法、Issuer、Audience、时间和必需 Claims。

- [ ] **Step 4：定义 Refresh Token 与会话生命周期**

明确 Refresh Token：

- 只交给 Knowledge Auth API；
- 数据库存储哈希而非明文；
- 每次刷新执行轮换，旧 Token 立即作废；
- 检测到已轮换 Token 重放时撤销同一 Token Family；
- 退出撤销当前 Family，管理员禁用撤销用户全部 Family；
- 过期、撤销、重放和用户禁用均返回统一认证失败，不泄露内部原因。

同时定义登录、刷新、退出的状态变化和事务边界。

- [ ] **Step 5：定义用户禁用与实时授权语义**

明确禁用后：

- 新登录和刷新立即失败；
- 新建 Chat、Research、上传和管理写操作失败；
- 两个服务对关键写入和 Internal Retrieval 执行用户当前状态检查；
- 已签发 Access Token 不因仅能验签而获得永久有效性；
- 正在运行的研究任务由 Research 状态规则进入受控取消或失败，不继续发起新的内部检索或外部调用；
- 历史审计信息保留。

- [ ] **Step 6：定义服务间认证和授权上下文**

Research → Knowledge 请求必须携带：

- 可验证的 Research 服务身份；
- Platform User ID；
- `request_id` 与调用链 ID；
- 目标知识库集合；
- Contract 版本。

Knowledge 按顺序验证服务身份、用户存在且启用、请求结构、每个 KB 的当前 READ 权限。服务凭证不授予 KB 权限；Research 传入的“已授权”布尔值无效。

- [ ] **Step 7：定义资源授权与证据实时复核**

引用 PRD §8 的矩阵，不复制整张表。补充：

- 管理员治理权限与资源所有权分别判断；
- 报告可保留内部 Evidence 的标题、引用标识和历史结论，但展开原文必须请求 Knowledge；
- 权限撤销后原文请求失败，报告不得缓存正文绕过校验；
- 外部 URL 不受 KB 权限控制，但仍受安全 URL 策略约束。

- [ ] **Step 8：定义敏感数据外发策略**

建立四级决策：来源分类 → Provider 类型 → 显式允许策略 → 脱敏与审计。必须规定：

- 内部内容进入互联网搜索词默认禁止；
- `hybrid` 的内部检索查询与外部搜索查询分别生成；
- 私有原文发送外部 LLM 默认拒绝，只有部署策略显式允许且记录 Provider、用途、数据分类和请求摘要时才可外发；
- 日志、Trace 和错误响应不记录完整私有正文或凭证；
- 无法确认分类或策略时失败关闭。

- [ ] **Step 9：定义审计、轮换、失败和验收场景**

审计事件至少覆盖登录、刷新重放、退出、禁用、管理员治理、Internal Retrieval 拒绝、内部证据复核和外发策略拒绝。验收场景至少覆盖：

1. 正常登录并跨两个服务使用同一身份；
2. 错误 Algorithm/Issuer/Audience/过期 Claim 被拒绝；
3. Refresh 轮换与重放检测；
4. 用户禁用后登录、刷新、创建任务和内部检索均失败；
5. 服务凭证有效但用户无 KB 权限时仍失败；
6. 报告创建后撤销 KB 权限，内部原文立即不可展开；
7. 私有内容未获外发许可时搜索和模型调用失败关闭；
8. 密钥轮换窗口内新旧验证密钥按明确时限兼容。

- [ ] **Step 10：运行身份规范检查并确认 GREEN**

重新运行 Step 1 命令，再运行：

```bash
rg -n 'TBD|TODO|FIXME|待补充|以后实现' docs/IDENTITY_AND_ACCESS.md
git diff --check -- docs/IDENTITY_AND_ACCESS.md
```

预期结果：章节检查退出码 `0`；占位符扫描无输出；`git diff --check` 无输出。

- [ ] **Step 11：提交身份与权限规范**

```bash
git add docs/IDENTITY_AND_ACCESS.md
git commit -m "docs: define unified identity and access model"
```

---

### Task 3：编写统一 API 协议规范

**Files:**
- Create: `docs/API.md`

**Interfaces:**
- Consumes: `docs/IDENTITY_AND_ACCESS.md`；PRD §7—§9、§13；ARCHITECTURE §4、§8—§10、§13；Task 1 的文档边界。
- Produces: Contract、Database、Pipeline 和 Frontend 规范共同引用的 HTTP、错误、端点及 SSE 表面。

- [ ] **Step 1：创建 API 规范验收检查并确认 RED**

运行：

```bash
python3.12 - <<'PY'
from pathlib import Path

path = Path("docs/API.md")
assert path.exists(), "API.md does not exist"
text = path.read_text()
required = [
    "## 1. 目标与边界",
    "## 2. 协议与版本",
    "## 3. 通用请求约定",
    "## 4. 通用响应与错误",
    "## 5. Auth API",
    "## 6. Knowledge API",
    "## 7. Chat 与 Conversation API",
    "## 8. Research Task API",
    "## 9. Evidence 与 Report API",
    "## 10. Admin API",
    "## 11. Internal Retrieval API",
    "## 12. Chat SSE",
    "## 13. Research SSE",
    "## 14. 健康、就绪与指标",
    "## 15. 兼容、废弃与契约测试",
    "## 16. 验收映射",
]
missing = [heading for heading in required if heading not in text]
assert not missing, missing
PY
```

预期结果：失败，提示文件不存在。

- [ ] **Step 2：定义协议、版本和通用请求约定**

明确：

- JSON 使用 UTF-8，时间使用带 `Z` 或显式偏移的 RFC 3339；
- 外部正式路由为 `/api/v1/*`，内部路由为 `/internal/v1/*`；
- `Authorization: Bearer` 的细节引用身份文档；
- `X-Request-ID` 可由可信客户端传入，否则网关生成；跨服务继续传播；
- 资源 ID 使用不透明字符串，API 使用 UUID 表达但客户端不得推断顺序；
- 列表接口统一 `page`、`page_size`，默认 20、最大 100；
- 排序字段使用显式允许列表，默认排序逐资源说明；
- 创建 Research Task 和其他可重试创建操作支持 `Idempotency-Key`；
- `POST` 创建同步资源返回 `201`，异步任务接受返回 `202`，删除无正文返回 `204`。

- [ ] **Step 3：定义统一响应与错误模型**

成功响应不强制额外 envelope；列表返回 `items`、`page`、`page_size`、`total`。错误固定为：

```json
{
  "error": {
    "error_code": "RS_TASK_CONCURRENCY_LIMIT",
    "message": "当前运行中的研究任务已达到上限，请稍后重试。",
    "request_id": "01J...",
    "retryable": true,
    "details": {}
  }
}
```

定义错误命名空间：`AUTH_*`、`KB_*`、`DOC_*`、`CHAT_*`、`RS_*`、`EVIDENCE_*`、`REPORT_*`、`INTERNAL_*`、`SYSTEM_*`。给出 HTTP 映射，至少覆盖 `400/401/403/404/409/413/422/429/500/502/503/504`。`details` 只能包含安全、结构化、可操作字段。

- [ ] **Step 4：定义 Auth、Knowledge、Document 端点目录**

至少列出方法、路径、权限、同步/异步、成功状态和主要失败：

- `/api/v1/auth/login|refresh|logout|me`；
- `/api/v1/knowledge-bases` 及 `/{kb_id}`；
- `/{kb_id}/documents`、`/{document_id}`、重试处理和来源位置访问；
- public/private READ 与 owner/admin WRITE 语义引用 PRD §8；
- 上传成功创建记录并分发入库时返回 `202`；
- 未完成入库的文档不能作为有效检索来源。

- [ ] **Step 5：定义 Chat 与 Conversation 端点目录**

至少定义：

- `/api/v1/chat/stream`：创建或继续问答，返回 Chat SSE；
- 独立取消当前生成的端点或断连取消语义，二者的幂等行为明确；
- `/api/v1/conversations` 列表、详情、重命名和删除；
- 请求中的 KB 范围每次实时校验；
- 多轮上下文不能扩展原 KB 范围；
- 检索或生成失败不返回伪造完成事件。

- [ ] **Step 6：定义 Research Task 端点目录**

至少定义：

- 创建、列表、详情、取消、恢复、删除；
- `knowledge|web|hybrid` 来源策略校验；
- `knowledge`/`hybrid` 至少一个当前可读 KB，`web` 不接受内部 KB；
- 创建接口使用 `Idempotency-Key`，返回 `202`；
- 取消与恢复是幂等命令；
- 并发/队列限制返回 `429` 和可重试错误；
- Task、Phase、Step 的枚举由 Research Pipeline 定义，API 只声明外部结构与未知枚举兼容规则。

- [ ] **Step 7：定义 Evidence、Report 与 Admin 端点目录**

至少定义：

- Task Evidence 列表/详情和关系查询；
- Report 读取、章节、引用定位和 P1 导出接口的版本边界；
- 内部证据原文通过 Knowledge 来源访问端点实时复核权限；
- 外部证据返回 URL 与获取时间；
- Admin 用户启禁、内容审计、治理删除和允许的元数据修正；
- Admin 不能替普通用户上传业务文档；
- 危险管理操作要求审计原因和幂等语义。

- [ ] **Step 8：定义 Internal Retrieval API**

至少定义 `POST /internal/v1/retrieval/search`，并明确：

- 请求和响应的完整字段 Schema 由 `packages/contracts/` 指定版本拥有；
- HTTP 层携带服务身份、用户授权上下文、`X-Request-ID` 和 Contract 版本；
- Knowledge 逐个 KB 实时校验 READ；
- 结果只返回 Contract 允许的内部 Evidence 信息；
- 服务认证失败、用户禁用、KB 越权、版本不支持、限流和 Provider 失败使用稳定错误码；
- Nginx 外部访问 `/internal/v1/*` 必须失败；
- 不公开 Chroma Collection、SQLAlchemy Model、磁盘路径或缓存 Key。

- [ ] **Step 9：定义 Chat SSE**

规定 `Content-Type: text/event-stream`、UTF-8、事件含 `event`、`id`、JSON `data`。事件目录至少包含：

- `meta`：请求和会话上下文；
- `message.delta`：回答增量；
- `sources`：已确认来源摘要；
- `error`：流内安全错误；
- `done`：唯一成功终态。

定义心跳注释帧、单调事件 ID、顺序、终态后禁止业务事件、断开取消生成以及已持久化内容的恢复边界。Chat 不使用 Research 的 Task/Phase/Step 事件。

- [ ] **Step 10：定义 Research SSE**

研究事件目录至少包含：

- `snapshot`：重连时的持久状态快照；
- `task.updated`；
- `phase.updated`；
- `step.updated`；
- `evidence.added`；
- `report.updated`；
- `error`：订阅或可公开任务错误；
- `stream.end`：本次订阅结束，不等同于任务成功。

定义 `Last-Event-ID`/游标、快照优先、重复事件可幂等消费、断线不取消任务、取消/恢复走 HTTP 命令，以及 Task 真正终态来自持久状态解析器。

- [ ] **Step 11：定义健康、兼容与验收映射**

明确 liveness、readiness、管理员/内部 dependency detail、内部 `/metrics` 的访问边界。兼容策略包括：

- 迁移期旧路由保持原行为；
- 兼容适配层不得改变权限和错误安全边界；
- 废弃必须有替代路径、调用方清单、时间窗和回归测试；
- Breaking Change 使用新版本；
- Contract 必须有 Provider/Consumer 固定样例测试。

在 §16 建立 PRD P0 映射表，覆盖 `FR-ID-001`、`FR-KB-001..003`、`FR-QA-001..002`、`FR-RS-001..004`、`FR-EV-001..004`、`FR-RP-001..003`、`FR-AD-001..002` 和 PRD §13 十个验收场景。

- [ ] **Step 12：运行 API 规范检查并确认 GREEN**

重新运行 Step 1 命令，再运行：

```bash
rg -n 'TBD|TODO|FIXME|待补充|以后实现' docs/API.md
rg -n '/api/v1/|/internal/v1/retrieval/' docs/API.md
git diff --check -- docs/API.md
```

预期结果：章节检查退出码 `0`；占位符扫描无输出；路径扫描同时命中外部与内部命名空间；`git diff --check` 无输出。

- [ ] **Step 13：提交 API 规范**

```bash
git add docs/API.md
git commit -m "docs: define EvidSight API protocol"
```

---

### Task 4：执行第一批跨文档一致性验收

**Files:**
- Verify: `docs/PRD.md`
- Verify: `docs/ARCHITECTURE.md`
- Verify: `docs/ROADMAP.md`
- Verify: `docs/IDENTITY_AND_ACCESS.md`
- Verify: `docs/API.md`
- Verify: `docs/superpowers/specs/2026-07-31-remaining-design-docs-first-batch-design.md`

**Interfaces:**
- Consumes: Tasks 1—3 的全部文档。
- Produces: 第一批规范完成证据和后续 `packages/contracts/` 设计的稳定输入。

- [ ] **Step 1：运行占位符与格式检查**

```bash
rg -n 'TBD|TODO|FIXME|待补充|以后实现' \
  docs/PRD.md docs/ARCHITECTURE.md docs/ROADMAP.md \
  docs/IDENTITY_AND_ACCESS.md docs/API.md
git diff --check HEAD~3..HEAD
```

预期结果：占位符扫描仅允许 PRD/ROADMAP 中对尚未创建专项文件使用明确的“待编写/待设计”，不得出现未决需求；`git diff --check` 无输出。若提交数量不是三次，改为对五个目标文件执行 `git diff --check`。

- [ ] **Step 2：运行本地 Markdown 链接检查**

```bash
python3.12 - <<'PY'
import re
from pathlib import Path

files = [
    Path("docs/PRD.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/IDENTITY_AND_ACCESS.md"),
    Path("docs/API.md"),
]
missing = []
for source in files:
    for target in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", source.read_text()):
        if "://" in target or target.startswith("mailto:"):
            continue
        resolved = (source.parent / target).resolve()
        if not resolved.exists():
            missing.append(f"{source}: {target}")
assert not missing, "Missing links:\n" + "\n".join(missing)
print("local markdown links: PASS")
PY
```

预期结果：输出 `local markdown links: PASS`。尚未创建的文件应使用代码路径而非 Markdown 链接，避免制造失效链接。

- [ ] **Step 3：运行权威边界与关键语义检查**

```bash
python3.12 - <<'PY'
from pathlib import Path

identity = Path("docs/IDENTITY_AND_ACCESS.md").read_text()
api = Path("docs/API.md").read_text()
architecture = Path("docs/ARCHITECTURE.md").read_text()

assert "服务凭证" in identity and "不能替代" in identity
assert "实时" in identity and "READ" in identity
assert "/api/v1/" in api
assert "/internal/v1/retrieval/" in api
assert "Chat SSE" in api and "Research SSE" in api
assert "断开" in api and "不得取消研究任务" in api
assert "packages/contracts/" in api
assert "不复制" in api or "不得复制" in api
assert "Research Service" in architecture and "禁止" in architecture
print("authority and protocol invariants: PASS")
PY
```

预期结果：输出 `authority and protocol invariants: PASS`。

- [ ] **Step 4：核对 PRD P0 覆盖映射**

```bash
python3.12 - <<'PY'
from pathlib import Path

api = Path("docs/API.md").read_text()
required = [
    "FR-ID-001",
    "FR-KB-001", "FR-KB-002", "FR-KB-003",
    "FR-QA-001", "FR-QA-002",
    "FR-RS-001", "FR-RS-002", "FR-RS-003", "FR-RS-004",
    "FR-EV-001", "FR-EV-002", "FR-EV-003", "FR-EV-004",
    "FR-RP-001", "FR-RP-002", "FR-RP-003",
    "FR-AD-001", "FR-AD-002",
]
missing = [item for item in required if item not in api]
assert not missing, missing
print("PRD P0 API mapping: PASS")
PY
```

预期结果：输出 `PRD P0 API mapping: PASS`。

- [ ] **Step 5：检查最终工作区范围**

```bash
git status --short
git log -4 --oneline
```

预期结果：本计划的三个实施提交只涉及五个目标文档；计划开始前已有的其他未提交状态保持不变。

- [ ] **Step 6：记录验收结果**

在任务交付消息中记录 Step 1—4 的实际命令、退出码和结果。若检查需要修复，修改对应文档并追加一个范围明确的提交：

```bash
git add docs/PRD.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/IDENTITY_AND_ACCESS.md docs/API.md
git commit -m "docs: resolve first-batch specification inconsistencies"
```

没有修复时不得创建空提交。

---

## 完成定义

- 五个目标文档已按各自唯一职责完成或对齐；
- 第一批设计规格的全部验收条件均有对应检查；
- PRD P0 功能可映射到公开端点、内部端点或 SSE 行为；
- 身份和 API 规范可以直接作为 `packages/contracts/` 设计输入；
- 所有验证均为本次实际执行结果；
- 未触碰既有无关工作区修改。
