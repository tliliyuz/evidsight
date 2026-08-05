# ADR-008：Research 任务生命周期、租约与恢复策略

- 状态：accepted
- 日期：2026-08-05
- 里程碑：M3
- 命中的 ADR 检查项：5、6
- 接受：负责人 2026-08-05 裁决「创建 ADR（A/B/C 三份）」并评审接受为 accepted

## 背景

M3 需要让 Research 深度研究任务具备可取消、可恢复、可审计的闭环：Worker 可能在任意外部调用或 LLM 调用之间崩溃；v1.0 基线为单 Worker、concurrency 1，但部署重启或扩容仍可能出现同一 Task 的双 Worker 竞争。若任务状态、Step 提交和租约语义不统一，会出现重复执行已完成 Step、两个 Worker 同时写业务结果、取消后仍发布报告、恢复后无法从安全断点继续等问题。

该选择决定 Research 任务状态机、并发一致性、恢复可靠性与幂等语义的长期机制，影响 `research_tasks`/`research_steps`/`agent_events` 表结构、Task 状态枚举、SSE 事件来源与恢复扫描行为。因此命中 ADR 检查项 5（核心机制）与 6（不可逆性——持久化格式与状态语义形成长期兼容承诺）。

## 决策

### MySQL 为任务生命周期唯一权威

- 任务、Step、发布 Revision 的状态与业务结果以 MySQL 事务为唯一事实源；Redis/Celery 不作为任务事实来源，消息丢失或重复不改变完成事实。
- Task 状态固定为 `pending|running|paused|completed|partially_completed|failed|canceled`；终态不可恢复为 running，重新研究必须创建新 Task。
- 只有 `TaskStateResolver` 可写终态，依据数据库中的 Step、Evidence、发布 Revision、取消请求、完整度和错误事实计算结果，而非 Worker 声明。

### 条件更新租约

- 租约字段为 `research_tasks.lease_owner`、`lease_expires_at` 与单调递增 `lease_generation`。
- Worker 领取与续租使用条件更新（WHERE 匹配当前 owner 与 generation）；Step 提交必须与 Task 的 owner、generation 同事务校验。
- 失去租约的 Worker 立即停止，不提交业务结果；过期 Worker 的迟到提交因 generation 不匹配被拒绝，不覆盖恢复 Worker 的结果。
- 租约时长、续租周期与扫描间隔的关系由部署配置约束，不硬编码在业务逻辑。

### 安全 Checkpoint 与 attempt

- 可复用 Checkpoint：Planning、每个 Web Search/Fetch Step、Evidence Reference 固化、Graph Build 与 Report Revision 发布；业务结果与 Step `completed` 同事务提交。
- Internal Retrieval、Rerank、Synthesis 只记录结构化安全摘要，不保存内部 excerpt；恢复需要内部语义工作集时重新 Internal Retrieval 并创建新 attempt。
- 同一逻辑 Step 重试递增 `attempt_count`；依赖失效时从 Searching 重建候选闭包，记录恢复 attempt 与输入摘要变化，不声称逐字复现。

### 取消与恢复

- 取消接口只持久化 `cancel_requested_at`；Worker 在安全点检查，取消后不得开始新外部调用或发布新 Revision；取消与完成竞态以报告发布事务开始前的条件检查为界。
- Recovery Scanner 查找 running 且租约过期的 Task，锁定后复核状态与 generation，将遗留 running Step 转 `retrying` 或 `failed`，清除旧 owner，重投递到 `research.execute`（与 API 创建共用执行队列）；启动扫描、周期扫描与手动恢复复用同一恢复服务。
- 幂等键 `(user_id, idempotency_key)` 唯一，同 Key 不同 `request_fingerprint` 拒绝；非幂等外部操作保存 Provider 幂等键或独立操作记录。

## 后果

- 单 Worker 崩溃后可从持久 Checkpoint 恢复，不重复已完成结果，不产生新旧 Worker 并发写冲突。
- 双 Worker 竞争时只有当前 generation 可提交；Redis 丢失/重复投递不影响完成事实。
- 取消安全生效后不产生业务结果；报告发布原子性以事务为界。
- 状态投影（Phase 聚合、Step 状态、SSE 事件）全部由数据库事实派生，重连不依赖 Redis 历史。

## 被否决方案

### Redis/Celery 状态作为任务事实源

崩溃与消息丢失会使状态与真实完成事实脱节，无法满足 AC-004 恢复成功率 ≥95% 的可审计要求。否决。

### 无租约、任务级锁覆盖整个生命周期

单 Task 长生命周期持锁导致恢复死锁，无法区分崩溃与慢处理。否决。

### 独立 recovery 队列

恢复路径与 API 创建路径分叉，恢复语义与正常执行不一致，增加维护负担。否决。

## 重新评估触发条件

- 引入多 Worker 并发或分布式事务能力；
- 单 Worker 并发 1 基线变化，需要并行执行子问题或 LLM 调用；
- Task 状态枚举、租约语义或 SSE 事件来源需要改变。

## 与既有 ADR 的关系

- 不改变、不推翻既有 accepted ADR。
- 对齐 [ADR-003](ADR-003-internal-evidence-no-content.md)：恢复不持久化内部正文，重取通过 Knowledge 实时鉴权。
- 对齐 [ADR-002](ADR-002-service-boundary.md)/[ADR-005](ADR-005-unified-identity-service-auth-egress.md)：恢复执行重新走 Internal Retrieval 授权顺序，用户禁用或 KB 撤权按当前事实处理。

## 相关规范

- [Research Pipeline](../../services/research/docs/RESEARCH_PIPELINE.md) §4、§13、§14
- [Research 数据库](../../services/research/docs/DATABASE.md) §5、§8
- [API 与事件协议](../specs/API.md) §8、§13
