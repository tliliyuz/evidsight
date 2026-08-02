# TESTING — 测试与发布验证策略

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 规范基线 |
| 最后更新 | 2026-08-02 |

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
- 登录、Refresh Rotation、重放撤销和退出；
- 禁用用户不能登录、刷新、创建任务、Chat 或 Internal Retrieval；
- private/public、owner/admin 操作矩阵；
- Internal Retrieval 任一 KB 无权时整批失败且检索未执行；
- 历史报告展开内部来源时实时复核权限。

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
