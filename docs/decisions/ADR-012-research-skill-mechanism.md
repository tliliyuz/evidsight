# ADR-012：Research Skill 机制（可扩展研究类型、数据源注册与报告库）

- 状态：proposed
- 日期：2026-08-17
- 命中的 ADR 检查项：2、3、5、7、8（1、4 潜在，一并裁决）
- 接受：待负责人评审

## 背景

招商背调（政府招商尽调）垂直应用需要三项能力：①多数据源（Tavily 公开网页 + 天眼查/企查查登录墙结构化数据：工商、司法、行政处罚、经营异常）；②报告持久化与「LLM wiki 循环」——报告库按 skill/region 检索历史报告保持风格一致，政府内部材料入库后内外结合检索；③长沙本地化（模拟数据用长沙企业，报告标题「长沙市××区××企业招商调查报告」）。

现状约束（已核对代码与规范）：

- `services/research/app/pipeline/planner.py` 的 `_TASK_TYPE_STRATEGIES` 与 `_CHANNEL_BY_STRATEGY` 硬编码 `comparison|explainer|analysis` 三型；`reranker.py` 同样读硬编码 task_type 默认值。
- `searcher.py` 直接调用 `_call_tavily`，无数据源注册抽象；新增天眼查连接器无法插拔。
- 报告以不可变 `report_revisions` 发布（ADR-009），无 skill/region 元数据，无法按领域检索历史报告。
- `ARCHITECTURE.md §1.2` 非目标明确「v1 不做通用 Agent 平台、插件市场或工作流编辑器」；`RESEARCH_PIPELINE.md §1` 同样声明 v1 不做「通用 Agent 平台」。

若以「内建 Skill 机制」让招商背调作为第一个 Skill 挂接：引入 Research 新职责与外部目录信任边界（项 2）；扩展公共契约 task_type/skill_id/报告元数据（项 3）；为核心 Pipeline 选择可扩展性长期方案（项 5）；同时修改 ARCHITECTURE / RESEARCH_PIPELINE / API / CONFIGURATION 四份规范（项 7）；把「插件机制」作为长期例外落地（项 8）。ADR-009 报告 Schema 扩展（新增元数据列）触发其「报告 Schema 需要改变」的重新评估条件（项 1 潜在）；skill 目录含数据源密钥配置涉及敏感信息处理（项 4 潜在）。故命中检查表并创建本 ADR。

## 决策

### 1. 通用 Research Skill 注册机制（core 内建、内容外置）

- core 新增 skill 加载器，目录约定：`skill.yaml`（id、name、描述、支持的 task_type、报告 schema 引用）+ 提示词模板 + 报告模板 + 数据源连接器声明。
- 扫描内置 `skills/`（只放通用示例，如「行业研究」，不含任何长沙/招商内容）+ 外部 `EVIDSIGHT_SKILLS_DIR`（公司/垂直内容，个人仓库零污染）。
- skill 是声明式配置与模板包，不执行任意代码；加载时严格校验 `skill.yaml` Schema，未知字段拒绝。

### 2. 管线解耦：task_type 策略由 skill 注入

- `planner.py` / `reranker.py` / `renderer.py` 的硬编码策略表改为「读 skill 配置注入」：无 skill 时保持 v1 三型默认行为（向后兼容），skill 可声明自己的 task_type 值（如 `due_diligence`）与规划/渲染策略段。
- ResearchPlan 结构（`sub_questions` / `questions` / `planned_channels`）不变，完整度算法与 Evidence Graph 不变。

### 3. 数据源注册表

- 定义连接器接口（search / fetch / structured），Tavily 改造为内置 web 连接器（行为不变），天眼查作为可选结构化数据连接器（工商/司法/处罚/经营异常），按 skill 声明启用。
- 连接器密钥经配置注入（环境变量），不提交仓库、不落日志；调用仍受预算、限流与审计约束（对齐 budget_service 与成本核算）。

### 4. 报告库与 skill 元数据

- `report_revisions` 新增可空元数据列（skill_id / region / company，向后兼容，不入 required）；发布事务不变，ADR-009 原子发布保留。
- 报告库检索：按 owner + skill/region 检索本人历史报告，作为风格样本注入提示词（「循环：生成 → 入库 → 下次同风格」）；不跨用户共享报告或 Evidence，不改变权限模型。

### 5. 长沙定制内容全部在 Skill 侧

- 长沙提示词、区县配置、天眼查适配器配置、政府内部材料 → 外部 Skill 目录；标题「长沙市××区××企业招商调查报告」由 skill 报告模板定义；基座不绑定长沙。

## 后果

- 收益：引擎能力（知识库、证据图谱、报告发布、SSE、审计）被垂直应用完整复用；换城市/政府 = 新建 skill 包，机制不动；个人仓库零公司 IP。
- 代价：公共契约扩展（task_type 新值 + skill_id + 报告元数据）形成兼容承诺；ARCHITECTURE §1.2 与 RESEARCH_PIPELINE §1 非目标需修订为「v1 不含通用插件市场，但含受控 Skill 扩展机制」；管线测试面扩大（skill 注入路径与默认路径双验证）。

## 被否决方案

### 方案 B：招商背调完全独立（仅文档级共享报告规范）

复用不到 evidsight 引擎（知识库、证据图谱、报告发布、SSE），报告风格一致性靠「自觉」对齐，无法满足领导「LLM wiki 循环 / 个性化」诉求。否决。

### 方案 C：轻量挂接（只加 task_type 值 + 元数据列，不建通用机制）

仍是改契约而非通用机制；每接一个垂直场景都要改 core，扩展性与「换提示词/数据源即复用」目标不符；且同样需要改公共契约，规避不了门禁。否决。

## 重新评估触发条件

- 需要第三方共享或公开 Skill 市场（涉及模板/代码信任执行）——需沙箱或签名设计；
- 报告库需要跨用户共享或跨租户检索（改变权限模型，需新 ADR）；
- skill 需要声明任意代码插件（改变信任边界，需新 ADR）；
- 数据源连接器数量增长，需要独立进程或并发策略调整。

## 与既有 ADR 的关系

- ADR-002（服务边界）：不改变双服务数据所有权与 Internal Retrieval 边界；天眼查连接器属 Research 自有外部依赖，不进 Knowledge 边界。
- ADR-008（任务生命周期）：不改变 Task/Phase/Step 状态机、租约与恢复语义；skill 元数据只作为任务配置字段。
- ADR-009（统一 Evidence Graph 与报告表达）：核心（Evidence Graph、不可变 Revision、原子发布、完整度算法）全部保留；本 ADR 仅扩展报告元数据投影，并明确报告库检索边界（owner 本人、不跨用户共享），即为其重新评估触发条件「报告 Schema 需要改变」的裁决。

## 相关规范

- [总体架构](../specs/ARCHITECTURE.md) §1.2（非目标修订）
- [Research Pipeline](../../services/research/docs/RESEARCH_PIPELINE.md) §1、§5.2（task_type 策略注入）
- [API 与事件协议](../specs/API.md) §8（ResearchTaskCreate：skill_id 可选、task_type 新增值）
- [配置](../specs/CONFIGURATION.md)（EVIDSIGHT_SKILLS_DIR、天眼查密钥键）
- [ADR-009](ADR-009-unified-evidence-graph-report.md)
