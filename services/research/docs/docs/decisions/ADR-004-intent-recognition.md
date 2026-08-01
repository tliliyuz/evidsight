# ADR-004 — 增加意图识别门控层

| 属性 | 值 |
|:---|:---|
| 状态 | 已采纳 |
| 日期 | 2026-07-02 |
| 决策人 | yuz |

## 背景

当前系统缺少意图识别层：用户输入 "你好" 等问候/闲聊类内容时，`AgentRuntime` 仍会启动完整七阶段 Research Pipeline（Planning → Search → Fetch → Rerank → Synthesis → Evidence Graph → Render），产生不必要的延迟、Token 与搜索成本。需要在 Pipeline 入口前增加一道「意图识别门控」，对非研究类输入直接返回友好回答，对真正研究主题保持现有流程不变。

## 决策

采用**同步 API 层混合门控**：

1. **规则快路径**：编译正则/关键词识别 obvious 问候、致谢、告别、自我介绍、过短输入。
2. **研究关键词快路径**：命中明确研究关键词时直接返回 research，避免为 obvious 研究主题调用 LLM。
3. **LLM 回退**：规则未命中且输入较短（≤120 字符）时，调用轻量 LLM 输出 JSON 分类。
4. **研究意图**：保持原流程，创建 `pending` 任务 + Planning Step，Celery 分发。
5. **非研究意图**：同步创建 `status=completed` 任务，预写一条 `report_sections` 单章节和一条空的 `evidence_graph` Step，使 `GET /report` 与历史列表直接可用。

## 未采纳方案

- **新增 Pipeline Phase**：把意图识别作为第 0 阶段。该方案仍需 Celery Worker 调度与至少一次 LLM 调用，无法节省非研究输入的延迟与 Token，不符合「门控」定位。
- **纯 LLM 分类**：对每次请求都调用 LLM，成本高于规则快路径， greetings 等 obvious 输入无需 LLM。
- **不持久化直接回答任务**：直接返回 API 而不创建任务记录，会导致历史列表缺失、无法审计，与 ResearchMind「可审计」定位冲突。

## 影响

- **DB 模型**：不新增列/ENUM。`research_tasks.status` 复用 `completed`；`requirements.task_type` 扩展为 `direct_answer`（系统设置）。
- **API 契约**：`POST /api/research` 响应增加 `direct_answer` 与 `report` 字段；直接回答任务不触发 Celery。
- **前端交互**：`taskStore.createTask()` 检测到 `direct_answer=true` 后直接切到完成态并加载报告，不建立 SSE。
- **可观测性**：直接回答任务同样 emit `completed` 状态转换，保持监控完整性。

## 实现文件

- `app/services/intent_classifier.py`
- `app/services/research_service.py`
- `app/api/research.py`
- `app/schemas/research.py`
- `frontend/src/stores/task.js`
- `frontend/src/views/ResearchPage.vue`

## 相关文档

- [API.md §3.1 POST /api/research](../../resource/docs/API.md#31-任务生命周期)
- [ARCHITECTURE.md §2.4 意图识别门控](../../docs/ARCHITECTURE.md#24-意图识别门控)
- [RESEARCH_PIPELINE.md §1.4 意图识别门控](../../docs/RESEARCH_PIPELINE.md#14-意图识别门控)
- [DATABASE.md §2.2 research_tasks](../../docs/DATABASE.md#22-研究任务表-research_tasks)
- [FRONTEND.md §4.2 三种页面状态](../../frontend/docs/FRONTEND.md#42-三种页面状态)
