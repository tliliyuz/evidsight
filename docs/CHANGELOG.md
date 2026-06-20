# CHANGELOG — 变更日志

> 本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 格式。
>
> 版本号使用 [语义化版本](https://semver.org/lang/zh-CN/)：`MAJOR.MINOR.PATCH`。
>
> 分类：`Added`（新增）、`Changed`（变更）、`Deprecated`（弃用）、`Removed`（移除）、`Fixed`（修复）、`Security`（安全修复）。

---

## [Unreleased]

> 项目处于设计阶段，尚未开始编码。以下为初始化条目。

### Added
- 项目初始化：创建 ResearchMind 仓库
- 产品需求文档 [PRD.md](PRD.md)
- 架构设计文档 [ARCHITECTURE.md](ARCHITECTURE.md)
- 研究管线设计文档 [RESEARCH_PIPELINE.md](RESEARCH_PIPELINE.md)
- 接口文档 [API.md](API.md)
- 数据库设计文档 [DATABASE.md](DATABASE.md)
- 基础设施复用清单 [INFRASTRUCTURE_REUSE.md](INFRASTRUCTURE_REUSE.md)
- 版本演进路线 [ROADMAP.md](ROADMAP.md)
- 开发指南 [DEVELOPMENT.md](DEVELOPMENT.md)
- 项目入口 [README.md](../README.md)
- 前端交互设计文档 [FRONTEND.md](FRONTEND.md)
- 前端基础设施复用清单 [INFRASTRUCTURE_REUSE_FRONTEND.md](INFRASTRUCTURE_REUSE_FRONTEND.md)
- 前端 UI 样式规范 [UIDESIGN.md](UIDESIGN.md)（Design Token `--rm-*` 体系，提取自 `ai_studio_code.html` 静态原型）

### Fixed
- API.md §5.3：E3107 `recoverable` 从 `false` 修正为 `true`（与 RESEARCH_PIPELINE.md §8.7/§8.9 一致——Render 失败可复用 Evidence Graph 重渲）
- ARCHITECTURE.md line 77：API.md 交叉引用从 §2 修正为 §3（研究任务接口）
- ROADMAP.md line 20：API.md 交叉引用从 §2 修正为 §3（研究任务接口）
- ARCHITECTURE.md line 195：DATABASE.md 交叉引用从 §3 修正为 §2（表结构）
- 初始化迁移 `7685a032ccd7_init` 执行失败修复：
  - `users.updated_at` 的 `server_default=(UTC_TIMESTAMP()) ON UPDATE UTC_TIMESTAMP()` 为 MySQL 语法错误——`ON UPDATE` 子句引用非 `CURRENT_TIMESTAMP` 表达式须加括号。改用 `CURRENT_TIMESTAMP` + ORM `onupdate`，对齐 docmind 模型层
  - `research_sources.uk_task_url` 此前以全列 `UNIQUE (task_id, url)` 建索引，`url VARCHAR(2048)` 超出 MySQL 3072 字节索引长度限制（错误 1071）。改回 DATABASE.md §2.4 规定的前缀唯一索引 `uk_task_url (task_id, url(255))`

### Changed
- 时区实现统一到 docmind 模型层方案（[DATABASE.md §0](DATABASE.md#0-时区约定)）：
  - 新增 `app/models/_types.py::UTCDateTime` TypeDecorator（impl=`DateTime`，写入转 UTC 剥离 tzinfo / 读取附加 UTC tzinfo），替换原 `DateTime(timezone=True)`
  - 所有 `created_at` / `updated_at` 服务端默认值由 `(UTC_TIMESTAMP())` 改为 `func.current_timestamp()`；`updated_at` 自动更新由 DDL `ON UPDATE` 改为 ORM `onupdate=func.current_timestamp()`
  - `utcnow()` 返回值由 naive UTC 改为 aware UTC datetime，与 `UTCDateTime` 兼容
  - 涉及模型：`user` / `refresh_token` / `research_task` / `research_step` / `research_source` / `evidence_item`
- `research_sources.uk_task_url` 模型声明由 `UniqueConstraint` 改为 `Index(..., unique=True, mysql_length={"url": 255})`，与 DATABASE.md §2.4 前缀索引规格一致
- DATABASE.md §0 时区约定重写：补充 `UTCDateTime` 双向转换说明、`CURRENT_TIMESTAMP` 选择理由、`updated_at` 由 ORM `onupdate` 维护；表结构中 `research_tasks.created_at` / `evidence_items.created_at` 的 `(UTC_TIMESTAMP())` 与 `users.updated_at` 的 DDL `ON UPDATE` 同步移除
- 时区复用规格文档对齐（根因修复：INFRASTRUCTURE_REUSE.md §5.1 原将 DocMind 源标注为 `UTCDateTime`，却把 ResearchMind 实现规格写成 `DateTime(timezone=True)`，与已验证的 docmind 实现矛盾——实现者照文档复刻即引入时区 bug。现以 docmind 实际实现为准统一全部文档）：
  - `INFRASTRUCTURE_REUSE.md §5.1` 重写为唯一权威规格：DocMind 源更正为 `app/models/_types.py::UTCDateTime` + `core/database.py` 的 `SET time_zone='+00:00'`；复用方式为「直接复制，零改动」；明确**禁止**裸 `DateTime`/`DateTime(timezone=True)`/`(UTC_TIMESTAMP())`，并声明本节为时区实现唯一规格、其余文档交叉引用
  - `CLAUDE.md` 时区条款：`ORM DateTime(timezone=True)` → 改为「必须用 `UTCDateTime`，禁止裸 `DateTime`/`DateTime(timezone=True)`，禁止 `(UTC_TIMESTAMP())`」并交叉引用 §5.1
  - `DEVELOPMENT.md §6.2` 四层 UTC 表「后端 (ORM)」行：`DateTime(timezone=True)` → `UTCDateTime` TypeDecorator；§时区规范同步改写并交叉引用 §5.1
  - `ROADMAP.md` 时区策略行：`app/core/database.py — ... + DateTime(timezone=True)` → `app/models/_types.py（UTCDateTime）+ app/core/database.py（SET time_zone='+00:00'）`，交叉引用 §5.1
  - 确认 `.claude/commands/review.md` 评审规则（裸 `DateTime` 视为 🔴 严重问题）本已正确，无需改动

	- 复用基础设施文档全面审计与对齐（根因扩展：时区矛盾是系统性问题——INFRASTRUCTURE_REUSE.md 虚报了 docmind 不存在的功能/组件，导致项目文档描述的复用能力与实际可复制代码不匹配。逐项核查 docmind 源码，修正全部 10 项严重不一致 + 5 项中等问题）：
	  - **INFRASTRUCTURE_REUSE.md 虚报修正**（docs/INFRASTRUCTURE_REUSE.md）：
	    - §2.1 LLM 客户端：`Anthropic SDK` → `OpenAI 兼容 SDK (openai 库)`；去掉"已封装 Anthropic SDK 的 `messages.create()`/`messages.stream()`"虚报；去掉"重试逻辑是通用基础设施"虚报（docmind 零重试代码）；错误处理从 `timeout/rate_limit/auth_error` 修正为仅 `rate_limit`；文件行数 ~150→222
	    - §2.3 Prompt Builder：去掉"单条 Evidence 截断"为 docmind 已有功能的虚报——docmind 的 `prompt_builder.py` 不做逐条截断，仅整条跳过/包含
	    - §3.1 SSE：去掉 `seq` 序号为 docmind 已有功能的虚报（docmind 无 seq 字段）；去掉"重连快照模式"为 docmind 已有功能的虚报（docmind SSE 是单向一次性生成器，无重连/快照）；修正复用范围为仅传输层（StreamingResponse + 心跳 + `event:type\ndata:json` 格式）
	    - §3.2 Trace：去掉"context manager 模式"虚报——docmind 的 `TraceRecorder` 无 `__enter__`/`__exit__`，使用普通对象方法记录模式
	    - §3.3 Reranker：去掉 `RerankInput`/`RerankOutput` 数据类虚报——docmind 不存在这些类，实际使用 `RetrievalOutput`/`RetrievalResult`
	    - §4.1 BM25：`ChromaDB（向量路由）三级缓存` → `进程内 dict + Redis 两层缓存 + MySQL 懒加载回源`；文件行数 ~400→686
	    - §4.2 Sentence Matcher：去掉"改引用格式正则"误标——引用正则在 `evidence_auditor.py`，`sentence_matcher.py` 只有中文标点切句正则；"段落切分"→"句级切分"（以标点符号切句）
	    - §4.4 Evidence Auditor：修正自相矛盾（"改引用格式正则…零改动"），改为"直接复制，零改动——引用格式 `[来源N]` 完全相同"；审计结果改为"ResearchMind 需自行决定"
	    - §1.2 Exceptions：文件行数 ~50→~266；复用方式明确错误码重新编号和 detail 类型扩展为 [Deviation]
	    - 底部汇总表重写：按"可直接复制"/"需改造适配"/"需重写"三类分组，行数/描述全部修正
	  - **项目文档 [Deviation] 标注**：
	    - `API.md §1.2`：新增 [Deviation] 说明 `detail` 为结构化 JSON 对象，与 docmind 基类 `detail: str` 不同，实现时需扩展 `AppException` 构造函数
	    - `API.md §1.4`：新增 [Deviation] 说明认证错误码段从 docmind E5xxx 重新编号为 E1xxx
	    - `ARCHITECTURE.md §4.3`：新增 [Deviation] 标注 `require_admin` 代码示例中 `detail` 传 dict
	    - `ARCHITECTURE.md §5.7`：SSE 事件有序规则明确 `seq` 序号为 ResearchMind 自行设计，非 docmind 已有
	    - `CLAUDE.md` 异常约定：更新为 `detail` 为结构化 JSON 对象，`dict | str` 双类型
	    - `RESEARCH_PIPELINE.md §11.2`：新增 [Deviation] 说明 trace 为成本+计时双模型，与 docmind 纯计时模型不同
	  - **设计原则确立**：
	    - 项目文档（API/ARCHITECTURE/DATABASE/RESEARCH_PIPELINE）是 ResearchMind 的独立设计蓝图，不标注"复用 docmind 设计"
	    - INFRASTRUCTURE_REUSE.md 是施工快照，仅指向可复制的 docmind 源文件，不参与设计决策
	    - 实现细节以 docmind 源码为准，项目文档描述与其一致（零矛盾）。故意改造之处标注 `[Deviation]`

### Deprecated
- 无

### Removed
- 无

### Security
- 无

---

## [0.1.0] — 2026-06-20（设计阶段）

### Added
- 完成全部 7 份设计文档初稿
- 确立文档驱动开发流程与归属矩阵
- 确立 Infrastructure Reuse 策略（从 DocMind 复用 Auth、LLM、异常体系、SSE 流式推送）
