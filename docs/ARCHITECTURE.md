# ARCHITECTURE — 架构设计文档

| 属性 | 值 |
|:---|:---|
| 文档版本 | v1.1 |
| 最后更新 | 2026-06-30 |

> 本文档是 **系统架构、技术选型、研究任务状态机（三层模型）、权限模型、非功能需求** 的唯一真理源。相关定义禁止在其他文档中重复，应使用交叉引用链接到本文档对应章节。实现进度和开发排期见 [ROADMAP.md](ROADMAP.md)。

---

## 1. 技术选型

| 层面 | 技术 | 说明 |
|:---|:---|:---|
| 后端框架 | FastAPI | 异步 Python，原生 SSE |
| 异步任务 | Celery + Redis | 任务编排 + 断点续跑 |
| LLM | deepseek-v4-pro (DeepSeek SDK) | MVP 单一模型，后续分级 |
| 搜索 | Tavily API | 含内容提取 |
| Rerank | BM25 + LLM Rerank | 粗筛 + 精排 |
| 关系数据库 | MySQL + aiomysql + SQLAlchemy 2.0 async | 所有业务数据 |
| 迁移 | Alembic | 所有 schema 变更走迁移脚本 |
| 部署 | Docker Compose | 4 服务：FastAPI + Celery Worker + Redis + MySQL |
| 时区 | 四层 UTC 统一 | MySQL → 后端 → API → 前端全链路 UTC |

---

## 2. 系统分层与 Pipeline 架构

### 2.1 系统分层（核心引擎 vs 表达层）

ResearchMind 架构分为两层，**核心引擎由 Agent Runtime 驱动，产出 Evidence Graph（结构化认知资产），表达层将其渲染为不同形态的报告**。

> **历史演进**：v0.x 为 Plan-then-Execute Workflow Engine，`PipelineOrchestrator` 按固定七阶段串行调度。v1.0 演进为 **Phase-Locked ReAct**：LLM 通过 Tool Calling 在每个 Phase 内自主决策调用哪个 Phase Tool，`AgentRuntime` 负责 ReAct Loop、Working Memory、Execution Context 与状态流转。旧 `PipelineOrchestrator` 仍保留在代码库中但已标记为 deprecated，仅作历史参考与紧急回退，不用于新任务。

```
┌─────────────────────────────────────────────┐
│            Presentation Layer               │
│  Report Render (模板驱动，可多形态输出)       │
├─────────────────────────────────────────────┤
│            Core Research Engine             │
│                                             │
│  Planning → Search → Fetch → Rerank →       │
│  Synthesis → Evidence Graph Build           │
│                                             │
│  核心产物：Evidence Graph                    │
│  (结构化认知资产，独立于任何报告格式)          │
└─────────────────────────────────────────────┘
```

**为什么要分层？**

| 混在一起 | 分开 |
|:---|:---|
| Synthesis 和 Report 耦合，换报告模板需重跑全 Pipeline | Evidence Graph 是稳定中间产物，Report Render 可单独重跑 |
| 无法支持「同一 research 产出技术版 + 投资版」两份报告 | 一个 Graph → 多模板渲染 |
| 报告格式变更侵入核心引擎 | 表达层独立演进 |

### 2.2 Pipeline 七阶段定义

| 阶段 | 所属层 | 核心职责 |
|:---|:---|:---|
| **Planning** | Core | LLM 拆解研究主题为可并行检索的子问题 |
| **Search** | Core | 调用 Tavily API，获取 URL + 标题 + 摘要 |
| **Fetch** | Core | 网页内容抓取 + 正文提取 + 截断 |
| **Rerank** | Core | BM25 + LLM Rerank，按相关性+信息量排序 |
| **Synthesis** | Core | LLM 跨源综合、冲突识别、观点聚类 |
| **Evidence Graph Build** | Core | 构建段落→证据→来源的结构化映射，**全流程的核心资产** |
| **Report Render** | Presentation | 按 task_type 选择模板，渲染 Markdown + 引用锚点，组装最终 JSON |

七阶段不再是硬编码调用链，而是 **Agent Runtime 的 Phase-Locked ReAct Loop 中的可调用工具集**。`AgentRuntime` 维护当前 `phase`，每一轮 LLM 只能在当前 phase 允许的 Tool 集合中选择（如 `searching` phase 主要工具为 `search_tool`），阶段目标达成后由系统推进到下一 phase。这种「ReAct 推理 + Phase 阶段锁」的混合架构既保留 Agent 的灵活性，又保证七阶段业务语义和可审计性。

> 各阶段输入/输出数据结构的完整定义（含类型、校验规则、失败策略）见 [RESEARCH_PIPELINE.md §1.2](RESEARCH_PIPELINE.md#12-pipeline-全览)。
> Agent Runtime、Tool System、Working Memory 的详细设计见 [ARCHITECTURE.md §2.3](#23-agent-runtime-核心机制)。历史决策记录见 `docs/decisions/ADR-001-agent-runtime-phase1.md`、`ADR-002-agent-runtime-phase2.md`、`ADR-003-agent-runtime-phase3.md`。

**`task_type` 如何驱动各阶段策略**（`task_type` 必填，直接决定 Planner 拆解策略、Rerank 排序维度、Report Render 模板选择，不能用「LLM 自己猜」替代）：

| task_type | Planner 策略 | Rerank 偏好 | Report 模板 |
|:---|:---|:---|:---|
| `comparison` | 对比矩阵拆解 | 属性对齐度 | 对比表 + 逐维度分析 |
| `explainer` | 研究方向聚类 | 观点新颖度 | 按研究方向组织章节 |
| `analysis` | 因果链拆解 | 因果关联度 | 威胁→影响→应对递进结构 |

> `task_type` 的产品定义与示例见 [PRD.md §1.4](PRD.md#14-研究任务类型)。各策略的完整算法（System Prompt、参数、输出 Schema）见 [RESEARCH_PIPELINE.md §2.4](RESEARCH_PIPELINE.md#24-planner-策略按-task_type)。

> 研究任务的输入 / 输出数据契约（Request / Response 模型）见 [API.md §3 请求与响应模型](API.md#3-请求与响应模型)。Pipeline 各阶段的 Prompt 模板、算法策略、SSE 事件映射等深度设计见 [RESEARCH_PIPELINE.md](RESEARCH_PIPELINE.md)。

---

## 2.3 Agent Runtime 核心机制

ResearchMind v1.0 的执行引擎是 **Phase-Locked ReAct Agent**：在保留 ReAct「推理 → 行动 → 观察」循环的同时，用 `phase` 作为安全 harness，保证七阶段业务语义、可审计性与断点续跑能力。Agent Runtime 由 `AgentLoop`、`PhaseController`、`ToolRegistry`、`WorkingMemory` 四个核心组件组成，它们的关系如下：

```
┌─────────────────────────────────────────────┐
│              AgentRuntime                   │
│  ┌─────────────┐  ┌─────────────────────┐  │
│  │ AgentContext │  │   PhaseController   │  │
│  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────────────────────────────┐   │
│  │            AgentLoop                │   │
│  │  while not finished:                │   │
│  │    LLM → tool_calls → execute()     │   │
│  │    → observation → WorkingMemory    │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │         ToolRegistry                │   │
│  │  7 phase tools + finish_tool        │   │
│  │  + memory_tool                      │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### 2.3.1 ReAct Loop 控制流

**Phase-Locked ReAct** 的定义：Agent 仍按 Planning → Search → Fetch → Rerank → Synthesis → Evidence Graph → Render 的固定顺序推进，但在每个 phase 内，LLM 可基于当前上下文多次调用该 phase 允许的 Tool；当该 phase 的 primary tool 成功执行后，`PhaseController` 自动推进到下一阶段。

**单轮循环控制流程**：

1. `AgentLoop` 检查 `AgentContext.finished` 或 `current_phase is None`，满足则退出循环。
2. 构造 LLM 消息：system prompt（含 phase 顺序、当前 phase、已完成 phase、当前阶段主工具）+ `WorkingMemory.to_messages()` + 当前 phase 用户级指令。
3. `PhaseController.get_available_tools()` 返回当前 phase 可用 Tool 列表（当前 phase tool + `finish_tool` + `memory_tool`）。
4. 调用 `chat_completion(messages, tools=tool_schemas, tool_choice="auto")`。
5. 若 LLM 返回 `reasoning_content`，发布 `agent.thought` SSE。
6. 解析 `tool_calls`；对每个 `ToolCall`：
   - 发布 `agent.action` SSE。
   - `PhaseController.is_tool_available(name)` 校验；若不可用，直接返回错误 observation。
   - `AgentRuntime._execute_tool()` 创建/复用 `ResearchStep`、调用 `Tool.execute()`、写入 Step 状态与 output、发布 `step.*` SSE。
   - 发布 `agent.observation` SSE。
   - 将 `ReActEntry` 写入 `WorkingMemory`。
   - 若当前 phase 的 primary tool 成功执行，调用 `mark_phase_done()`。
7. 本轮全部 Tool Call 处理完成后，若 `current_phase_done`，调用 `advance()` 推进到下一 phase。
8. `AgentContext.iteration_count` 自增，进入下一轮。

**终止条件**：

| 条件 | 触发位置 | 行为 |
|:---|:---|:---|
| 所有 phase 完成 | `PhaseController.advance()` 返回 False | `AgentContext.finished = True`，循环正常退出 |
| LLM 显式调用 `finish_tool` | `finish_tool.execute()` | `AgentContext.finished = True`，循环立即退出 |
| 达到最大迭代次数 | `AgentLoop.run()` 循环判断 | 抛出 `AgentLoopExhaustedError`，由 `AgentRuntime` 捕获后按证据阈值判定 Task 状态 |

**最大迭代次数**：由 `app/config.py` 的 `MAX_AGENT_ITERATIONS` 控制，默认 **30**。该上限用于防止 LLM 因 prompt 误解或 `memory_tool` 滥用而陷入无限循环；达到上限时任务通常标记为 `failed` 且 `recoverable=true`，用户可通过 Retry 继续执行。

**错误恢复策略**：

| 异常场景 | 处理方式 | 是否终止 Loop |
|:---|:---|:---|
| LLM API 调用失败 | 记录 observation "LLM 调用失败: {exc}" 到 `WorkingMemory`，继续下一轮 | 否 |
| LLM 返回 content 但未返回 tool_calls | 将 content 作为 observation 记录，继续下一轮 | 否 |
| LLM 请求了当前 phase 不可用的 Tool | 返回 observation "Tool 'x' 在当前 phase 不可用"，不创建 Step | 否 |
| Tool 参数校验失败 | `PhaseHandlerTool` 返回 `success=False` 的 `ToolResult`，`AgentRuntime` 标记 Step 失败 | 否 |
| Tool 执行抛异常 | `AgentRuntime._execute_tool()` 捕获并包装为 failed `ToolResult`，记录 Step 失败 | 否 |
| 达到 `MAX_AGENT_ITERATIONS` | `AgentLoop` 抛出 `AgentLoopExhaustedError` | 是（进入最终化） |

**Thought 解析与验证**：

- **Thought 来源**：LLM 返回的 `reasoning_content` 直接作为 thought 文本，不额外解析。
- **Tool Call 解析**：由 `app/core/llm.py` 将 LLM 原始响应解析为 `ToolCall` 列表（`id`/`name`/`arguments`）。
- **Phase 可用性校验**：`PhaseController.is_tool_available(name)` 在可用列表中查找，拒绝越权调用。
- **参数校验**：`validate_tool_params(params, schema)` 校验 JSON Schema 的 `required` 字段与 `properties` 中声明的基础类型（string/integer/number/boolean/object/array）。

### 2.3.2 Tool System

**Tool 抽象**：所有 Tool 遵循统一协议，Agent 只通过 Tool 与外部能力交互。

| 类型 | 定义 | 说明 |
|:---|:---|:---|
| `Tool` Protocol | `name` / `description` / `parameters_schema` / `mapped_phase` / `execute(ctx, **params) -> ToolResult` | 所有 Tool 必须实现 |
| `ToolResult` | `success` / `output` / `observation` / `error_message` / `cost` / `duration_ms` | Tool 执行产出 |
| `ToolCall` | `id` / `name` / `arguments` | LLM 发起的单次调用 |
| `ToolContext` | `task` / `step` / `session` / `sse_bridge` / `trace_recorder` / `agent_context` / `working_memory` | Tool 执行时注入的上下文 |

**Tool 注册与发现**：

- `ToolRegistry` 是 Tool 的唯一注册中心，内部维护 `dict[str, Tool]`。
- `register(tool)` 注册；`get(name)` 按名称查找；`list_tools(phase)` 按 `mapped_phase` 过滤；`to_openai_schema(phase)` 生成 OpenAI Function Calling schema。
- `build_default_tool_registry()` 在应用启动时构造默认 Registry：7 个 `PhaseHandlerTool`（包装既有 phase handler）+ `finish_tool` + `memory_tool`。
- `PhaseController` 从 Registry 获取可用 Tool，决定 LLM 每轮能看到的 Tool 集合。

**Tool Schema 格式**：采用 OpenAI Function Calling 格式，例如 `search_tool`：

```json
{
  "type": "function",
  "function": {
    "name": "search_tool",
    "description": "Search 阶段：根据子问题调用搜索 API 获取候选来源",
    "parameters": {
      "type": "object",
      "properties": {
        "reason": {"type": "string", "description": "调用原因"},
        "focus_sub_question_index": {"type": "integer", "description": "聚焦的子问题索引"}
      },
      "required": []
    }
  }
}
```

**输入校验与输出转换**：

- 输入校验：`validate_tool_params(params, schema)` 轻量校验，不依赖外部库；仅校验 `required` 存在性与 `properties` 声明的基础类型；不拒绝未知字段。
- 输出转换：`PhaseHandlerTool` 作为薄适配器，将现有 phase handler（如 `run_search(task, step, session, sse_bridge)`）包装为 Tool。handler 返回的 dict 直接作为 `ToolResult.output`；非 dict 结果包装为 `{"result": str(output)}`。
- 失败包装：handler 抛异常或参数校验失败时，`PhaseHandlerTool` 返回 `success=False` 的 `ToolResult`，`AgentRuntime` 据此标记 Step 失败。

**权限与副作用控制**：

- **Phase 级权限**：`PhaseController` 每轮仅暴露当前 phase tool + `finish_tool` + `memory_tool`，LLM 无法调用其他 phase 的 Tool；越权调用会收到错误 observation。
- **上下文隔离**：Tool 只能通过 `ToolContext` 访问 `task`、`step`、`session` 等资源，不能自行创建 DB 会话或访问全局状态。
- **业务逻辑不变**：`PhaseHandlerTool` 不修改底层 handler 内部逻辑，保证既有 Pipeline 算法与测试继续有效。
- **全局 Tool 约束**：`finish_tool` 结束 Agent Loop；`memory_tool` 仅操作内存级 `WorkingMemory`，v1.0 不实现 Long Memory 写入。

**内置 Tool 列表**：

| Tool | mapped_phase | 职责 | 参数示例 |
|:---|:---|:---|:---|
| `plan_tool` | `planning` | 拆解研究主题为子问题 | `reason` |
| `search_tool` | `search` | 多子问题搜索 | `reason`, `focus_sub_question_index` |
| `fetch_tool` | `fetch` | 网页抓取与正文提取 | `reason`, `target_url` |
| `rerank_tool` | `rerank` | BM25 + LLM 精排 | `reason`, `top_k` |
| `synthesis_tool` | `synthesis` | 跨源综合 | `reason`, `focus_cluster` |
| `evidence_graph_tool` | `evidence_graph` | 构建结构化证据图谱 | `reason` |
| `render_tool` | `render` | 渲染 Markdown 报告 | `reason` |
| `finish_tool` | — | 显式结束 Agent Loop | — |
| `memory_tool` | — | 读写内存级 Working Memory | `operation`, `key`, `value` |

### 2.3.3 Working Memory

Working Memory 是单次任务内的 ReAct Trace，记录 Thought / Action / Observation / Finish 全链路，既用于 prompt 上下文注入，也用于调试、审计与断点续跑。

**ReAct Entry 模型**：

```python
@dataclass
class ReActEntry:
    iteration: int              # Agent Loop 轮次
    phase: str                  # 所属 phase
    thought: str | None         # LLM reasoning_content
    tool_name: str | None       # Tool 名称
    tool_call_id: str | None    # LLM 分配的 tool_call_id
    arguments: dict             # Tool 调用参数
    observation: str | None     # Tool 执行结果摘要
    tool_output_summary: dict   # output 关键字段摘要
    step_id: str | None         # 关联 ResearchStep.id
    timestamp: datetime         # UTC 时间戳
```

`entry_type` 由字段推导：`finish_tool` → `finish`；`tool_name is not None` → `action`；`observation is not None` → `observation`；否则 → `thought`。

**容量管理**：

- 内存级 `WorkingMemory` 维护环形缓冲区，上限由 `AGENT_WORKING_MEMORY_MAX_ENTRIES` 控制，默认 **20**。
- 超过上限时丢弃最旧条目（FIFO），保留最近 N 条注入 prompt。
- `AgentLoop._summarize_output()` 仅保留 `sub_questions`、`total_results`、`evidence_count`、`clusters_count` 等关键计数字段，避免 prompt 过长。

**分层结构**：

| 层级 | 作用域 | v1.0 实现 | v2.0 规划 |
|:---|:---|:---|:---|
| 短期工作记忆 | 单次任务内 | `WorkingMemory` + `agent_memory_entries` 表 | 保持 |
| 长期记忆 | 跨任务共享 | `memory_tool` 返回未实现提示 | `memory_tool` 读写 Long Memory 存储 |

v1.0 的 Working Memory 仅覆盖单次任务；跨任务的用户偏好、领域知识、历史结论等 Long Memory 在 Phase 6（v2.0）实现。

**检索策略**：

- 按 `iteration` + `created_at` 排序重建时间线。
- `WorkingMemory.recent(n)` 返回最近 N 条记录。
- `to_messages()` 将 entries 转换为简化文本消息（思考/动作/观察）注入 LLM prompt。
- 断点续跑时，从 `agent_memory_entries` 按 `task_id` + `created_at DESC` 加载最近 N 条，恢复内存状态。

**持久化机制**：

- 专用表 `agent_memory_entries` 持久化 ReAct Trace，成为唯一真实来源；`execution_context` 不再写入完整 `working_memory` JSON。
- `WorkingMemory` 维护 `_pending_persist` 队列，记录自上次持久化以来新增的 entries。
- `AgentRuntime` 在 Step 完成/失败及 Loop 结束后统一调用 `AgentMemoryService.persist_pending_entries()` 批量 flush，保证事务边界清晰。
- 旧任务（Phase 1/2）首次恢复时，若 DB 为空则 fallback 读取 `execution_context.working_memory`，之后新 entries 进入 DB。

> 表结构、索引与外键详见 [DATABASE.md §2.9](DATABASE.md#29-agent-memory-entries-表-agent_memory_entries)。持久化策略的决策记录见 `docs/decisions/ADR-003-agent-runtime-phase3.md`。

## 3. 研究任务状态机

### 3.0 核心原则

**ResearchMind v1.0 是以 Agent Runtime 为核心的研究执行系统。** 状态机不是流程的附属品，而是系统的骨架。三层状态模型、Execution Context、Partial Failure Semantics 是断点续跑和 DAG 并发的根基。Agent 的 ReAct Trace（Thought / Action / Observation）持久化到 `agent_memory_entries` 表，成为调试、审计与断点续跑的新来源。

### 3.1 三层状态模型

```
🧠 Level 1：Task State（用户可见，对外 API）
─────────────────────────────────────────────
PENDING → RUNNING → COMPLETED
                 → PARTIALLY_COMPLETED
                 → FAILED
                 → CANCELED
                 → PAUSED [v2]

⚙️ Level 2：Phase State（Pipeline 阶段，决定"当前在做什么"）
─────────────────────────────────────────────
PLANNING → SEARCHING → FETCHING → RERANKING →
SYNTHESIZING → BUILDING_EVIDENCE_GRAPH → RENDERING

🔧 Level 3：Step State（执行单元，Agent Tool Call + DAG 的核心）
─────────────────────────────────────────────
PENDING → RUNNING → COMPLETED
                  → FAILED
                  → SKIPPED
                  → RETRYING
```

| 层级 | 概念 | 所有权 | 持久化 | 示例 |
|:---|:---|:---|:---|:---|
| Task State | 用户任务的宏观状态 | `research_tasks.status` | 每条任务一行 | "这个研究任务正在运行" |
| Phase State | 当前 Pipeline 阶段 | `research_tasks.current_phase` | 每条任务一个字段 | "当前在执行搜索阶段" |
| Step State | 每个 Tool Call / 子步骤的执行状态 | `research_steps.status` | N 条记录，按 parent_step_id 构成执行树 | "search_step_3 已完成，fetch_step_7 正在运行" |

**三层之间有严格的转换规则，禁止跨层判断：**

- Task 状态由 Step 完成情况**推导**，不直接设置
- Phase 状态随 Agent Loop 推进**单调前进**（由 `AgentRuntime` 的 `PhaseController` 管理）
- Step 状态由 Agent Runtime / Celery Worker 直接写入；同一 phase 内可因多次 Tool Call 存在多个 Step（如 Search 按子问题分多次调用）

### 3.2 Task State 转换规则

| 当前状态 | 目标状态 | 触发条件 |
|:---|:---|:---|
| `PENDING` | `RUNNING` | Celery Worker 拾取任务，首个 Phase 开始 |
| `RUNNING` | `COMPLETED` | 所有非 SKIPPED 的 Step 均为 COMPLETED |
| `RUNNING` | `PARTIALLY_COMPLETED` | 所有 Step 终态（COMPLETED / FAILED / SKIPPED），但至少一个 FAILED 或 SKIPPED，且满足 Evidence Completeness Threshold（见 §3.5） |
| `RUNNING` | `FAILED` | 致命 Step 失败（见 §3.5），或不满足 Evidence 最小阈值 |
| `RUNNING` | `CANCELED` | 用户主动取消，当前 Step 收到中断信号 |
| `RUNNING` | `PAUSED` | [v2] 用户暂停 |
| `PAUSED` | `RUNNING` | [v2] 用户恢复 |

> Task State **禁止**由任务自身直接写入（例如 Synthesis 完成不能直接 `UPDATE status='COMPLETED'`）。Task State 由 `TaskStateResolver` 统一计算：检查所有 `research_steps` 的终态后推导出 Task State。

### 3.3 Execution Context（断点续跑的核心）

```python
# research_tasks.execution_context 列（JSON）
{
    "current_phase": "FETCHING",           # Level 2: 当前 Pipeline 阶段
    "last_completed_step_id": "uuid-12",   # 最后完成的 Step
    "execution_pointer": {
        "phase": "FETCHING",
        "step_index": 3,                   # 当前 Phase 内的 Step 序号
        "total_steps_in_phase": 10
    },
    "progress": {
        "completed_steps": 15,
        "total_steps": 22,
        "estimated_remaining_ms": 45000
    },
    "agent_context": {                     # Agent Runtime 专用上下文（v1.0）
        "iteration": 12,                   # 当前 Agent Loop 轮次
        "working_memory_pointer": "uuid-xyz"  # 最近一次持久化的 ReAct Entry 指针
    }
}
```

**没有 Execution Context 的后果：**

| 场景 | 无 Execution Context | 有 Execution Context |
|:---|:---|:---|
| Celery Worker 崩溃重启 | 不知道恢复到哪一步，只能全量重跑 | 读取 `execution_pointer`，精确恢复 |
| DAG 并发 Barrier 恢复 | 不知哪些并行 Step 已完成，Barrier 永远挂起 | 遍历已完成 Step，跳过 Barrier 判断 |
| 用户请求 Retry | 不知道哪些阶段要重跑 | 从 `last_completed_step_id` 的下一个 Step 开始 |
| SSE 重连 | 不知道当前进度，无法推送 | 读取 `progress` 字段，立即推送当前状态 |

> Execution Context **在每个 Step 完成后原子更新**，与 Step 状态写入在同一个事务内。

### 3.4 Step 执行树（v1.0 Tree，v2.0 DAG）

**v1.0 线性执行树（Agent Runtime 下同一 Phase 可有多个 Step）：**

```
task
 └── step_01: PLANNING       (parent: NULL)
       └── step_02: SEARCH_1  (parent: step_01, phase: searching)
             └── step_03: SEARCH_2  (parent: step_02, phase: searching)
                   └── step_04: FETCH_1  (parent: step_03, phase: fetching)
                         └── step_05: FETCH_2  (parent: step_04, phase: fetching)
                               └── step_06: RERANK    (parent: step_05, phase: reranking)
                                     └── step_07: SYNTHESIS (parent: step_06, phase: synthesizing)
                                           └── ...
```

**同一 Phase 内的 ReAct 链（以 searching 为例）：**

```
iteration 1: agent.thought  → agent.action(search_tool, sub_question=...)
             → step: SEARCH_1 started/completed
             → agent.observation(results=[...])
iteration 2: agent.thought  → agent.action(search_tool, sub_question=...)
             → step: SEARCH_2 started/completed
             → agent.observation(results=[...])
iteration 3: agent.thought  → agent.action(finish_tool)
             → phase 推进到 fetching
```

`agent_memory_entries` 按 `iteration` / `entry_type`（thought / action / observation / finish）记录上述 ReAct Trace，与 `research_steps` 通过 `step_id` 关联。

**v2.0 并行 DAG（架构预留）：**

```
task
 └── step_01: PLANNING
       ├── step_02: SEARCH[子问题1]  ─┐
       ├── step_03: SEARCH[子问题2]  ─┤ 并行
       └── step_04: SEARCH[子问题3]  ─┘
              ├── step_05: FETCH[URL-1]
              ├── step_06: FETCH[URL-2]
              └── ...
```

`research_steps` 表结构设计见 [DATABASE.md §2 核心表结构](DATABASE.md#2-核心表结构)。

> **v1.0 备注**：MVP 使用 Tree 结构（`parent_step_id` 指向上一阶段），所有 Step 线性串行。v2 升级为真 DAG 时将引入 `step_edges` 关联表（`from_step_id`、`to_step_id`、`dependency_type`），`parent_step_id` 降级为显示用标记。

### 3.5 部分失败策略与 Evidence Completeness Threshold

> Step 类别的失败策略、重试次数、降级行为详见 [§5.5 Failure Model](#55-failure-model失败分类学)（架构真理源）。此处仅定义 Evidence Completeness Threshold——即部分失败时判定 PARTIALLY_COMPLETED vs FAILED 的边界条件。

**Evidence Completeness Threshold（证据完整性阈值）：**

```
min_evidence = max(5, ceil(max_sources * 0.4))

PARTIALLY_COMPLETED 判定：
  ✅ evidence_graph.items.length >= min_evidence
  → 即使有 Fetch 失败，报告质量可接受
  → Task State = PARTIALLY_COMPLETED

  ❌ evidence_graph.items.length < min_evidence
  → 报告质量不可接受
  → Task State = FAILED (insufficient_evidence)
```

> 阈值默认值：`min_evidence = max(5, ceil(max_sources * 0.4))`。管理员可通过 `requirements` 覆盖。

### 3.6 SSE 事件与状态同步

每个 Step 状态变更时，SSE 推送对应事件。Agent Runtime  additionally 推送 `agent.*` 事件暴露推理过程：

| Step 事件 | Task 事件 | Phase 事件 | Agent 事件（v1.0 新增） |
|:---|:---|:---|:---|
| `step.started` | — | `phase.started`（Phase 首个 Step 开始时） | `agent.thought`（LLM 思考内容） |
| `step.progress` | `task.progress`（携带 progress 快照） | — | `agent.action`（Tool Call 意图） |
| `step.completed` | — | `phase.completed`（Phase 内所有 Step 完成时） | `agent.observation`（Tool 执行结果） |
| `step.failed` | `task.warning`（可降级失败）或 `task.failed`（致命） | — | — |
| `step.skipped` | `task.warning` | — | — |
| — | `task.completed` | — | — |

> **SSE 重连恢复**：客户端断连后重连，服务端读取 `execution_context.progress` 立即推送一份完整的状态快照（`task.status.snapshot` 事件），包含当前 Task State、Phase、所有已完成 Step 摘要、`progress` 对象。此后恢复正常增量推送。SSE 事件协议完整定义见 [API.md §5 SSE 事件协议](API.md#5-sse-事件协议)。
> Agent 事件数据字段与示例见 [API.md §4.1](API.md#41-事件类型总览)。

### 3.7 TaskStateResolver

所有 Step 进入终态后触发 TaskStateResolver，按以下优先级推导 Task 最终状态：

```
1. 存在 FAILED 且 failure_type = FATAL？
   → Task = FAILED
2. 全部非 SKIPPED 的 Step 为 COMPLETED？
   → Task = COMPLETED
3. 存在 SKIPPED 或 FAILED（可降级）？
   → 统计 evidence_items 数量
      ├── >= min_evidence → PARTIALLY_COMPLETED
      └── < min_evidence  → FAILED (E3103 InsufficientEvidence)
```

**Agent Runtime 下的 Resolver 调整**：

- 同一 `phase` 可能产生多个同类型 Step（如多次 `search_tool` 调用），Resolver 按 `step_type` 分组判断「该 phase 是否已完成」。
- 若某 phase 已尝试（存在该 phase 的 Step）但存在非终态 Step，则任务仍处于 `running`。
- 全部 7 个 phase 均已尝试且无非阻塞非终态 Step 时，回退到 evidence threshold 判定 `partially_completed` / `failed`。
- 旧 Pipeline 路径（`PipelineOrchestrator`）的 Step 模型与上述逻辑兼容，因为每个 phase 仍映射到 `step_type`。

> `min_evidence` 计算见 [§3.5 Evidence Completeness Threshold](#35-部分失败策略与-evidence-completeness-threshold)。Resolver 由 Celery Worker 在每 Step 完成后调用，**禁止** Task 自身直接写入状态。

---

## 4. 权限模型

### 4.1 设计原则

权限分为两层，**禁止混用**：

| 层级 | 语义 | 函数 | 稳定性 |
|:---|:---|:---|:---|
| **Task Access** | "用户能否访问这个研究任务" | `require_task_accessible` | 最稳定，很少扩展 |
| **System Permissions** | "用户是否有系统级管理权限" | `require_admin` | 独立，可扩展角色 |

> **为什么不能合并？** Task 权限语义是「资源归属判断」（owner / admin 审计），System 权限语义是「角色能力判断」（谁能看统计、改配置）。合并后加 `moderator`、`readonly_admin`、`billing_admin` 等新角色时，`require_task_accessible` 会膨胀为 200 行 if-else。

### 4.2 CRUD 权限矩阵

| 操作 | owner | admin | 其他用户 |
|:---|:---|:---|:---|
| 创建研究任务 | ✅ | ✅ | ✅ |
| 查看/操作自己的任务 | ✅ | ✅ | ❌ |
| 查看/操作他人的任务 | ❌ | ✅（审计） | ❌ |
| 系统管理（统计/限流/审计日志） | ❌ | ✅ | ❌ |

### 4.3 实现层

```python
# app/core/permissions.py

async def require_task_accessible(task_id: str, user: User, db: AsyncSession) -> ResearchTask:
    """
    Task 级权限：检查用户是否有权访问该研究任务。
    - owner → 允许
    - admin → 允许（审计权限）
    - 其他 → 403
    """
    task = await db.get(ResearchTask, task_id)
    if not task:
        raise AppException(code="E2001")  # TaskNotFound
    if task.user_id != user.id and user.role != "admin":
        raise AppException(code="E2002")  # TaskNotOwned

    # [Planned: v1.5] 审计日志 hook
    # await audit_log("task_access", user_id=user.id, task_id=task_id)

    return task


async def require_admin(user: User) -> None:
    """
    System 级权限：检查用户是否是管理员。
    用于统计、限流配置、审计日志等系统级接口。
    
    [Deviation] detail 传 dict（结构化对象），基类 AppException.detail 为 str。
    见 API.md §1.2 [Deviation] 说明。
    """
    if user.role != "admin":
        raise AppException(
            code="E2009",
            detail={
                "error_type": "AdminRequired",
                "error_description": "该操作需要管理员权限"
            }
        )
```

### 4.4 未来角色扩展（v1.5+）

```
当前 (v1.0)                    未来 (v1.5+)
  user      admin              user  moderator  researcher  readonly_admin  billing_admin  admin
  │         │                   │       │           │             │               │          │
  │         ├─ Task Access      │       │           │             │               │          │
  │         ├─ System Perm      ├─Task──┤           │             │               │          │
  ├─Task───┤                   │       ├─System────┤             │               │          │
  └─ own only                   │       │           │             │               │          │
                                └─ own ─┴─ flagged ─┴─ own only ──┴─ billing ─────┴─ full ───┘
```

> **`require_task_accessible` 不变**——新增角色只需在判断条件中加 `user.role in ('admin', 'moderator')`，不会破坏已有体系。`require_admin` 函数按需升级为 `require_role(["admin", "billing_admin"])`。

---

## 5. 非功能需求

### 5.1 性能（端到端 Pipeline SLA）

| 阶段 | P50 | P95 | P99 |
|:---|:---|:---|:---|
| Planning | < 5s | < 10s | < 15s |
| Search | < 8s | < 15s | < 20s |
| Fetch | < 30s | < 60s | < 90s |
| Rerank | < 3s | < 5s | < 8s |
| Synthesis + Evidence Graph | < 20s | < 30s | < 45s |
| Render | < 5s | < 10s | < 15s |
| **端到端 (quick)** | **< 2min** | **< 3min** | **< 4min** |

### 5.2 并发与系统容量

| 指标 | v1.0 目标 | 说明 |
|:---|:---|:---|
| 并发任务数 | 20-50（取决于 LLM QPS） | 单节点 FastAPI + Celery |
| Celery Worker | 4-8 进程 | `--concurrency=4`，IO 密集型可上调 |
| 队列策略 | FIFO，Retry 任务优先出队 | 避免失败任务被正常流量饿死 |
| LLM 并发限制 | ≤ 3 并发（DeepSeek API 默认限额） | 通过 Celery 队列节流，不客户端限流 |
| 任务创建速率限制 | 5 次/分钟/用户 | Redis 固定窗口计数器 |

### 5.3 成本控制

Deep Research = Token Burning System。**每条任务必须有 Token 预算，不可无限消耗。**

| 预算项 | 限额 | 硬/软 |
|:---|:---|:---|
| Tavily Search 调用 | ≤ 5 次/任务 | 硬限制 |
| Fetch URL 数 | ≤ 15 个/任务 | 硬限制 |
| **单任务总 Token 预算** | **≤ 35K input + 15K output** | **软限制（超出告警但不截断）** |

> **成本估算（v1.0 单任务）**：约 50K tokens ≈ deepseek-v4-pro $0.15 + Tavily $0.05 ≈ **$0.20/task**。月 1000 任务约 $200。
>
> 各阶段 LLM token 限额（硬/软限制）与追踪时机见 [RESEARCH_PIPELINE.md §11](RESEARCH_PIPELINE.md#11-成本追踪与-token-预算)。

### 5.4 可靠性

| 指标 | 目标 |
|:---|:---|
| LLM 调用成功率 | > 99%（3 次重试） |
| Tavily API 可用性 | 不可控；降级策略见 §5.6 |
| Fetch 成功率 | > 70%（互联网网页天然有失败） |
| 任务完成率 | > 90%（含 PARTIALLY_COMPLETED） |
| 断点续跑恢复成功率 | 100%（从 `execution_context` 恢复） |
| Worker 崩溃自动恢复 | ✅（`acks_late` 重投递 + `running` 状态识别 + 任务级锁） |

#### 5.4.1 Worker 崩溃恢复

**问题**：Celery Worker 被 SIGKILL/OOM/断电杀死后，任务永久卡在 `running`（死锁）。`task_time_limit` 超时强杀同效。

**恢复依赖四层机制**：

| 层级 | 机制 | 职责 |
|:---|:---|:---|
| 传输层 | Celery `acks_late=True` | Worker 崩溃后未 ACK 任务自动重回 Redis 队列 |
| 入口层 | Pipeline 入口三元状态检查 | `pending`→正常执行 / `running`→崩溃恢复 / 终态→跳过 |
| 并发层 | 任务级租约锁 | 防止同一任务被两个 Worker 同时恢复；TTL 短、自动刷新、崩溃后快速过期 |
| 监察层 | 超时监察者（`_run_worker_timeout_watcher`） | 运行时持续扫描，主动发现并处置卡死任务 |

**关键设计决策**：

| 决策 | 值 | 理由 |
|:---|:---|:---|
| 任务级幂等锁 | **租约模式**：TTL = `CELERY_TASK_LOCK_TTL`（20s），Worker 执行期间每 `CELERY_LOCK_REFRESH_INTERVAL`（10s）刷新一次；崩溃后旧锁在 20s 内自动过期 | 相比固定长 TTL，租约模式在崩溃后快速释放锁（20s vs 900s），大幅缩短恢复窗口；正常执行期间锁持续续期，不会误过期 |
| 启动恢复阈值 | `STALE_TASK_RECOVERY_SECONDS`（60s） | 任务 `running` 超过 60s 且锁已过期即判定为过时，充分覆盖租约过期场景 |
| Step 锁遗留容忍 | TTL 600s 内恢复时当前 phase step 被跳过 | 未提交的 step output 本身已随 Worker 丢失，重新执行无副作用 |
| 启动恢复重入安全 | 多 FastAPI 实例同时检测同一过时任务 → 各自 re-queue → 任务锁保证只有一个 Worker 进入 | 无需实例间协调 |
| `task_time_limit` 不单独处理 | 超时 SIGKILL ≡ Worker 崩溃，统一覆盖 | 减少分支复杂度 |

> Pipeline 入口三元检查、`_start_task()` 恢复路径、`_create_step()` 复用逻辑等实现细节见 [RESEARCH_PIPELINE.md §10.5](RESEARCH_PIPELINE.md#105-worker-崩溃恢复)。启动恢复实现见 `app/main.py` `lifespan()`。任务锁实现见 `app/tasks/lock.py`。过时任务扫描与重新投递见 `app/tasks/recovery.py`。

**超时监察者（Worker Timeout Watcher）**：

FastAPI `lifespan()` 启动后台协程 `_run_worker_timeout_watcher()`，在运行时持续监控任务健康状态：

| 检查项 | 参数 | 行为 |
|:---|:---|:---|
| 任务级锁缺失 | 每 `WORKER_TIMEOUT_CHECK_INTERVAL`（5s）扫描所有 `running` 任务 | 检查任务级租约锁是否存在；锁缺失持续超过 `WORKER_TIMEOUT_SECONDS`（10s）且超过启动宽限期 `WORKER_TIMEOUT_GRACE_SECONDS`（5s）后，CAS 将任务标记为 `failed`（E3112，`recoverable=true`） |
| 长时间 `pending` 任务 | 同上扫描周期 | `started_at` 超过 `PENDING_TASK_TIMEOUT_SECONDS`（30s）仍为 `pending` 则标记 `failed`（E3113，`recoverable=true`） |
| Redis 不可用 | — | 跳过本轮判定，不误判（避免网络抖动导致误标 `failed`） |

> `recoverable=true` 表示该失败任务可在下次启动恢复时被重新投递。超时监察者实现见 `app/tasks/watcher.py`。

**`app/tasks/recovery.py` 模块**：

| 函数 | 职责 |
|:---|:---|
| `recover_stale_tasks(check_lock: bool)` | 扫描过时 `running` 任务并重新投递 |

两个入口调用 `recover_stale_tasks`：

| 入口 | `check_lock` 值 | 场景 |
|:---|:---|:---|
| FastAPI `lifespan()` 启动恢复 | `False` | 应用启动时，不检查锁（此时锁可能尚未建立），仅按 `STALE_TASK_RECOVERY_SECONDS` 判定过时 |
| Celery `worker_ready` 信号恢复 | `True` | Worker 就绪时，同时检查租约锁是否已过期，避免误回收正在执行的任务 |

### 5.5 Failure Model（失败分类学）

| 失败类型 | 来源 | 可重试？ | 重试次数 | 降级策略 |
|:---|:---|:---|:---|:---|
| `LLM_TIMEOUT` | LLM 调用超时 | ✅ | 3 | 无降级，重试耗尽 → FAILED |
| `LLM_RATE_LIMIT` | LLM API 限流 | ✅ | 3（指数退避） | 无降级，重试耗尽 → FAILED |
| `SEARCH_EMPTY` | 某子问题搜索返回 0 结果 | ❌ | 0 | 跳过该子问题，标记 SKIPPED |
| `SEARCH_BACKEND_DOWN` | Tavily API 完全不可用 | ✅ | 2 | 降级 Fallback Chain，全失败 → FAILED |
| `FETCH_TIMEOUT` | 单个 URL 超时 | ✅ | 1 | 跳过该 URL，标记 SKIPPED |
| `FETCH_403` | 单个 URL 拒绝访问 | ❌ | 0 | 跳过该 URL，标记 SKIPPED |
| `FETCH_EMPTY` | 抓取成功但无正文 | ❌ | 0 | 跳过该 URL，标记 SKIPPED |
| `RERANK_INVALID` | Rerank 输入格式错误 | ❌ | 0 | 无降级 → FAILED |
| `SYNTHESIS_FAILED` | LLM 综合失败 | ✅ | 3 | 无降级，重试耗尽 → FAILED |
| `PARTIAL_COMPLETION` | 非致命降级聚合（搜索/抓取部分失败） | ❌ | 0 | 见 §3.5 Evidence Completeness Threshold |
| `CELERY_WORKER_LOST`（E3112） | Worker 崩溃/丢失（超时监察者检测：任务级租约锁缺失超过阈值） | ✅（断点续跑） | 0 | CAS 标记 `failed`（`recoverable=true`），下次启动恢复时重新投递；HTTP 500 |
| `CELERY_WORKER_NOT_PICKED_UP`（E3113） | Worker 未在时限内拾取任务（`pending` 超过 `PENDING_TASK_TIMEOUT_SECONDS`） | ✅（断点续跑） | 0 | CAS 标记 `failed`（`recoverable=true`），下次启动恢复时重新投递；HTTP 500 |
| `AGENT_LOOP_EXHAUSTED` | Agent Runtime 达到最大迭代次数（`MAX_AGENT_ITERATIONS`）仍未完成当前 phase | ❌ | 0 | 当前 phase 标记失败，由 TaskStateResolver 按证据阈值判定 Task 状态；通常 recoverable=true |

### 5.6 Search/Fetch Fallback Chain

每个子问题独立执行搜索降级，每个 URL 独立执行抓取降级。v1.0 仅 Tavily + 直接 HTTP GET，不做缓存降级、不做搜索后端切换。v1.5 引入 SearXNG 作为兜底后端。

> 完整的降级链路（含重试间隔、HTTP 状态码映射、超时阈值）见 [RESEARCH_PIPELINE.md §3.4](RESEARCH_PIPELINE.md#34-失败策略) 和 [§4.5](RESEARCH_PIPELINE.md#45-失败策略)。

### 5.7 数据一致性与幂等性

| 规则 | 机制 | 违反后果 |
|:---|:---|:---|
| **所有 Step 执行必须幂等** | Step 执行前检查 `status`：已是 `completed` 则跳过执行；Step 级锁 `SET rm:step_lock:{step_id} NX EX 600` | 重试导致同 Step 重复执行 |
| **所有 Task 状态更新必须 CAS** | `UPDATE ... WHERE status = 'old_value'`，更新失败则重试 | 并发 Worker 导致状态覆盖错乱 |
| **Worker 崩溃恢复防并发** | 任务级租约锁 `SET rm:task_lock:{task_id} NX EX 20`（TTL = `CELERY_TASK_LOCK_TTL`），Worker 执行期间每 `CELERY_LOCK_REFRESH_INTERVAL`（10s）续期；`run()` 入口获取、`finally` 释放 | 两个 Worker 同时恢复同一任务 |
| **Evidence 只追加不覆盖** | `INSERT` only，Retry 不会删除已有 evidence 行 | 重试丢失已收集证据 |
| **Task-level Retry 创建新 Execution Context** | `retry` 操作新建 `execution_context`，不修改原始失败的 context | 断点续跑逻辑与原始执行冲突 |
| **SSE 事件有序** | 每个事件带 `seq` 序号（ResearchMind 自行设计），客户端丢弃 `seq < last_seen` 的事件 | 重连后事件乱序 |

### 5.8 安全

| 方面 | 措施 |
|:---|:---|
| 鉴权 | JWT Bearer Token，ResearchMind 自有 Auth 实现 |
| 任务隔离 | `require_task_accessible` 统一校验，严格 `user_id` 隔离 |
| 输入校验 | topic ≤ 500 字符，Pydantic Schema 严格校验 |
| URL 安全 | Fetch 前校验协议（仅 http/https）、禁止内网 IP、禁止 127.0.0.1 |
| 内容安全 | Fetch 内容长度截断（单页 100KB），响应体限制 2MB |
| 速率限制 | 创建任务 5 次/分钟/用户，API 调用 20 次/分钟/用户 |

### 5.9 可观测性

| 方面 | 措施 |
|:---|:---|
| 结构化日志 | 每 Step 开始/结束 JSON log，含 task_id + step_id + duration_ms |
| Trace 链路 | `research_tasks.trace` JSON + 各 Step `duration_ms` |
| SSE 事件 | 全 Pipeline 事件流可记录可重放 |
| 成本追踪 | 每任务记录 `total_tokens` + `estimated_cost` |
| Worker 健康检查 | `GET /api/health/workers` — Celery `control.ping()` 返回 worker 数量+名称列表 |

### 5.10 数据生命周期

DeepResearch 是「临时计算系统」，不是「永久知识库」。存储必须设置 TTL。

| 数据 | 保留期 | 过期行为 | 说明 |
|:---|:---|:---|:---|
| `research_tasks` + `research_steps` | 30 天 | Celery Beat 定时清理 | 用户可能回头查阅近期报告 |
| `report_sections` | 30 天 | 随 task CASCADE | — |
| `research_sources` | 30 天 | 随 task CASCADE | — |
| `evidence_items` | 30 天（可选 90 天） | 随 task CASCADE | 证据是核心资产，如需长期保留可配置 |
| `section_evidence` | 随 task CASCADE | — | — |
| SSE 事件日志 | 7 天 | 每日轮转 | 仅调试用 |
| 应用日志 | 14 天 | logrotate | — |

> 用户可主动「保存」报告（导出 PDF/Markdown），系统不承担永久存储责任。管理员可在 `requirements` 中覆盖 `ttl_days`。

---

## 6. 部署与运维

部署采用 Docker Compose，4 服务：**FastAPI + Celery Worker + Redis + MySQL**（技术栈见 §1）。

- **时区**：四层 UTC 统一（MySQL → 后端 → API → 前端）。所有 DATETIME 列存储 UTC，详见 [DATABASE.md §0 时区约定](DATABASE.md#0-时区约定)。
- **异步任务**：Celery + Redis 负责任务编排与断点续跑；Retry 任务优先出队（见 §5.2）。
- **Worker 崩溃恢复**：`acks_late=True` 保证未完成任务自动重投递；Pipeline 入口识别 `running` 状态进入恢复路径；任务级租约锁（TTL 20s，10s 续期）防并发恢复；启动时自动检测过时 `running` 任务并 re-queue；运行时超时监察者持续扫描卡死任务（见 §5.4.1）。
- **数据清理**：Celery Beat 定时清理过期任务数据（TTL 见 §5.10）。
- **迁移**：Alembic 管理数据库迁移，禁止手动改库。

> 具体开发环境、项目结构、环境变量、启动命令等开发指南将在 DEVELOPMENT.md 中补充。

---

## 7. 相关文档

- [产品需求文档](PRD.md)
- [研究管线设计文档](RESEARCH_PIPELINE.md)
- [接口文档](API.md)
- [数据库设计文档](DATABASE.md)
- [开发排期](ROADMAP.md)
