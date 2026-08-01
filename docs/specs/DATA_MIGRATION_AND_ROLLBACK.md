# DATA MIGRATION AND ROLLBACK — 数据迁移与回滚规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 迁移设计基线 |
| 最后更新 | 2026-08-01 |

## 1. 范围

本文定义 DocMind 与 ResearchMind 生产数据进入 EvidSight 三个逻辑数据库时的映射、验证、切换和回滚要求。Git 历史和代码布局迁移见 [MONOREPO_MIGRATION_PLAN.md](../plans/MONOREPO_MIGRATION_PLAN.md)。

## 2. 强制原则

- 先备份、恢复验证，再执行不可逆变换；
- 使用可重复运行的版本化脚本，禁止手工改生产表；
- 源数据在验收窗口内保持只读副本；
- 每批记录输入数量、成功、跳过、失败、校验和与游标；
- 迁移不改变权限、API、状态机或业务含义；无法无损映射的记录进入隔离清单，不静默丢弃；
- 密码哈希、Token、密钥、隐藏推理和无必要正文不得跨库复制。

## 3. 迁移顺序

1. 冻结源提交、Schema revision、数据快照和对象存储清单。
2. 建立 `platform_db` 用户映射表，生成稳定 Platform User UUID。
3. 迁移 Knowledge KB、Document、Document Version、Section、Segment、Conversation、Message 和来源引用。
4. 重建或验证 Per-KB Collection；不把旧 Chroma 内部 ID 当作外部标识。
5. 迁移 Research Task、Step、Web Source、Evidence、Report，并生成 revision 1。
6. 将 Research 内部来源转换为 KB、Document、Document Version、Segment 稳定 ID；不能闭合的记录标记隔离。
7. 执行双边计数、关系闭包、权限抽样、检索和报告引用验证。
8. 进入只读切换窗口，重放增量并完成最终校验。
9. 切换应用；源系统保持只读至回滚窗口关闭。

## 4. 身份映射

- 用户名只作为候选匹配键，不作为跨服务身份；
- 冲突账号必须人工决策，不自动合并；
- 迁移后统一使用 Platform User UUID；
- Research 不迁移自己的认证表和 Refresh Token；
- 禁用状态取更严格结果，启用不得自动恢复旧 Token 或任务。

## 5. Knowledge 映射

- KB/Document 保留稳定 UUID；缺失时按确定性迁移清单生成并固化映射；
- 每个现有成功文档创建初始 Active Document Version；
- Segment 获得稳定 UUID，并记录版本、顺序和位置；
- Conversation v1.0 只绑定一个 KB；无法确定范围的会话保留历史但禁止继续提问，进入人工清单；
- Message Source 不保存 Chunk 正文，只保存稳定来源身份和显示快照；
- Per-KB Collection 通过迁移脚本重建或校验 MySQL/向量 parity。

## 6. Research 映射

- 旧任务状态必须映射到新 Task/Step 状态；模糊终态不得自动标记 completed；
- 旧报告生成不可变 revision 1；
- Web URL 规范化并保留原始 URL、抓取时间和内容哈希；
- 内部 Evidence 必须闭合到 Document Version 和 Segment；旧正文不得进入 `evidence_items`；
- 旧隐藏推理、完整 Prompt 和非白名单 JSON 字段丢弃并记录数量。

## 7. 校验门禁

至少执行：

- 源/目标按表计数和状态分布；
- Platform User、KB、Document、Task 映射一一性；
- 外键、同 Task、同 Revision 和 Evidence 引用闭包；
- MySQL Active Version 与 Per-KB Collection parity；
- 随机抽样登录、private/public 权限、单 KB Chat、三类 Research、报告引用和撤权二次鉴权；
- 敏感字段静态扫描；
- 两个服务 Alembic head 和镜像版本记录。

所有偏差必须有记录、影响、处置和批准人。

## 8. 切换与回滚

回滚点包括：源数据库一致性备份、上传/向量卷同批次快照、旧镜像、配置键名清单和迁移前 revision。

满足任一条件立即停止切换并回滚应用：权限越权、引用大规模断裂、计数超出批准偏差、核心链路不可用或无法在 RTO 内完成。

数据库优先使用 expand/contract。已执行不可逆转换时不运行虚假的 downgrade；恢复备份或部署前滚修复。回滚后重新验证登录、权限、单 KB Chat、Research、SSE 和来源展开。

## 9. 迁移记录

实际批次大小、校验 SQL、源提交、快照、镜像 ID、执行时长、RPO/RTO 和偏差进入带日期的迁移记录，不覆盖本文规范。
