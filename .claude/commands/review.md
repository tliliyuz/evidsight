# /review — 据见项目代码审查

审查当前分支或用户指定范围的代码变更，对照据见权威文档、服务边界和质量规范，输出有证据的分级问题清单。

## 1. 确定审查范围

优先使用用户指定的 commit、分支或目录范围。用户未指定时：

1. 仓库已有远端主分支：审查 `origin/main...HEAD`。
2. 仓库尚无远端或首个提交：审查暂存、未暂存和未跟踪文件。
3. 输出实际审查范围，不得假定命令执行成功。

## 2. 识别受影响模块

按路径分类：

| 路径 | 模块 |
|---|---|
| `apps/web/` | 统一前端 |
| `services/knowledge/` | Knowledge Service |
| `services/research/` | Research Service |
| `packages/contracts/` | 跨服务契约 |
| `deploy/`、`docker-compose.yml` | 部署与基础设施 |
| `docs/` | 产品、架构与项目文档 |

读取所有变更文件的完整上下文；不要只依赖 diff 片段。

## 3. 读取权威文档

所有审查必须读取：

- `CLAUDE.md`
- `docs/PRD.md`

按变更范围增加：

| 变更 | 必读文档 |
|---|---|
| 架构、服务边界、部署 | `docs/ARCHITECTURE.md`、相关 ADR |
| API、错误码、SSE | `docs/API.md`、`packages/contracts/` |
| 数据库和迁移 | 对应服务 `docs/DATABASE.md` |
| Knowledge Pipeline | `services/knowledge/docs/RAG_PIPELINE.md` |
| Research Pipeline | `services/research/docs/RESEARCH_PIPELINE.md` |
| 前端页面和交互 | `apps/web/docs/FRONTEND.md` |
| 前端样式 | `apps/web/docs/UIDESIGN.md` |
| 需求和排期 | `docs/PRD.md`、`docs/ROADMAP.md` |

文件尚未建立时，应说明缺失；涉及相应设计的代码不得在无权威文档情况下被判定为完全通过。

## 4. 必查项

### 4.1 SDD 与测试先行门禁

- [ ] 变更前是否已有对应的权威规范或明确验收条件？
- [ ] 规范是否覆盖输入、输出、状态、失败、权限和兼容语义？
- [ ] 测试是否由规格和验收条件推导，而非根据实现反向编写？
- [ ] 新功能、Bug 修复或行为变更是否提供 RED 证据？
- [ ] RED 是否因目标行为缺失而失败，而非语法、Fixture、环境或 Mock 错误？
- [ ] GREEN 是否只包含通过当前测试所需的最小实现？
- [ ] 重构是否发生在测试全部通过之后，并保持外部行为不变？
- [ ] 是否提供本次实际执行的测试命令和关键结果？
- [ ] 纯文档、生成物、配置或 Spike 是否符合例外条件并记录理由？

以下情况标记为严重问题：无规格开发；生产行为先于测试；Bug 修复没有复现测试；测试从未正确失败；通过修改测试迎合错误实现；以手工测试代替自动回归测试。

### 4.2 服务边界

- [ ] Research 是否直接读取 Knowledge 的数据库、ChromaDB、上传目录或内部 Model？
- [ ] Knowledge 是否依赖 Research 的 Task、Agent Runtime 或 Evidence Graph 实现？
- [ ] 是否跨服务 import 对方的 `app` 包？
- [ ] 跨服务通信是否通过 `/internal/v1` 和明确 Contract？
- [ ] Contract 是否泄露 ORM、Collection 或缓存内部结构？
- [ ] 是否出现循环依赖或双向同步调用？

违反强制边界标记为严重问题。

### 4.3 身份、权限与数据安全

- [ ] 两个服务是否使用统一 JWT Claims 和禁用用户语义？
- [ ] Internal Retrieval 是否执行实时知识库权限校验？
- [ ] 报告内部证据原文是否重新校验当前权限？
- [ ] 是否把内部私有内容拼入互联网搜索请求？
- [ ] 外部模型调用是否符合脱敏、配置和审计策略？
- [ ] 是否存在硬编码密钥、Token、密码或本机敏感路径？
- [ ] 上传、路径、URL、SQL 和 Markdown 是否有注入或越权风险？

权限泄漏、敏感信息外发和注入风险标记为严重问题。

### 4.4 后端规范

- [ ] API 层是否只校验、鉴权并调用 service？
- [ ] IO 是否 async，DB Session 是否依赖注入？
- [ ] 正式接口是否使用 Pydantic Schema？
- [ ] 配置是否从 `settings` 获取？
- [ ] 时间是否统一 UTC 和 `UTCDateTime`？
- [ ] JWT Claims 提取是否防护异常并返回正确的 401？
- [ ] Celery 分发前是否提交业务事务？
- [ ] Key、队列和 Metric 是否带服务命名空间？
- [ ] 跨服务 ID 是否错误建立共享 ORM 关系？

### 4.5 Knowledge 专项

- [ ] visibility、ownership、admin 权限是否分离？
- [ ] 入库、检索、Rerank 和 Evidence 链路是否符合设计？
- [ ] 向量存储是否位于抽象层后？
- [ ] 文档删除是否同步处理数据、向量、缓存与文件？
- [ ] 页码/章节回溯是否避免全文重复搜索？

### 4.6 Research 专项

- [ ] 是否保持七阶段 Pipeline 顺序？
- [ ] Task/Phase/Step 状态是否由统一解析器计算？
- [ ] Step 是否幂等，Task 状态是否有并发保护？
- [ ] Evidence 是否按追加/版本语义处理？
- [ ] Retry 是否创建新 Execution Context？
- [ ] Worker 重载后是否再次检查取消/删除状态？
- [ ] 租约、恢复与 SSE 重连是否保留完整语义？
- [ ] Knowledge Search Tool 是否只依赖 Contract？

### 4.7 前端专项

- [ ] 是否使用 Composition API、`<script setup>`、Pinia 和 API 封装？
- [ ] 是否使用 `--es-*` Design Token，避免硬编码样式？
- [ ] Markdown 是否安全，原生 HTML 是否默认关闭？
- [ ] 危险操作是否二次确认并正确恢复 loading？
- [ ] Chat SSE 与 Research SSE 是否保持独立业务协议？
- [ ] 引用锚点和 Evidence 面板是否双向联动？
- [ ] API 时间是否由 `new Date(isoString)` 正确转换？

### 4.8 契约专项

- [ ] 是否先修改 Contract 再修改 Provider/Consumer？
- [ ] 是否存在字段删除、改名或语义变化造成 Breaking Change？
- [ ] Provider 与 Consumer 测试是否同时更新？
- [ ] Evidence 字段是否足以定位、授权和追溯来源？
- [ ] 新版本是否提供兼容或迁移路径？

### 4.9 测试质量

- [ ] 测试是否能明确指出哪项生产行为变化会使其失败？
- [ ] RED 与 GREEN 是否运行同一个目标测试，而不是中途更换断言？
- [ ] API 与 Service 层是否均有覆盖？
- [ ] 成功、失败和关键分支是否成对覆盖？
- [ ] 是否存在弱断言或条件断言？
- [ ] 是否复制生产逻辑到测试？
- [ ] Mock 是否放在外部边界并保留真实业务逻辑？
- [ ] 重复 Mock 样板是否提取？
- [ ] 变更契约时是否有 Provider/Consumer 测试？
- [ ] 完成声明是否附有本次实际测试输出？

### 4.10 文档一致性

- [ ] 实现是否符合产品与整合设计？
- [ ] TODO、待办、路线图和测试状态是否与代码一致？
- [ ] 行为变化是否更新 CHANGELOG？
- [ ] 重要决策是否新增或更新 ADR？
- [ ] 同一技术事实是否在多个文档重复定义并产生漂移？

## 5. 输出格式

```markdown
## 审查报告 — [范围]

### 审查范围
- 变更文件：N
- 影响模块：...
- 对照文档：...
- 验证命令：...

### 严重问题（必须修复）
按 文件:行号 列出问题、证据、影响和建议。

### 规范问题（建议修复）
按 文件:行号 列出问题、证据、影响和建议。

### 改进建议（可选）
只列与本次变更直接相关的建议。

### 服务边界与安全
说明边界、权限、数据外发和契约检查结果。

### 测试与验证
列出 RED 失败证据、GREEN 通过证据、完整验证命令、结果和未验证范围。

### 文档一致性
说明权威文档、CHANGELOG、ADR、TODO 和路线图状态。

### 通过项
列出经证据确认通过的关键检查项。
```

## 6. 审查原则

- 每条问题必须引用具体文件、行号和对应规则。
- 先检查 SDD/TDD 过程证据，再评价最终代码；最终有测试不代表遵循测试先行。
- 不把个人风格偏好当作缺陷。
- 不因测试存在就假定质量合格，必须检查断言和真实执行路径。
- 不因文档声称完成就假定代码完成，也不因代码存在就忽略文档缺失。
- 无法验证的内容明确标记为“未验证”，禁止推测通过。
- 代码与权威文档冲突时先报告，不自行修改设计迁就代码。
- 优先报告会导致越权、数据泄漏、错误结论、任务损坏或跨服务耦合的问题。
