# RELIABILITY — 运行可靠性与恢复规范

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 规范基线 |
| 最后更新 | 2026-08-08 |

> 本文定义生产运行、健康、容量、备份、恢复、发布与故障处理必须满足的结果和边界。三节点职责与网络拓扑以 [ARCHITECTURE.md](ARCHITECTURE.md) 为唯一权威来源；具体执行步骤见 [运维操作指南](../guides/OPERATIONS.md)。

ADR 检查 1–8：否。本文由原 `specs/OPERATIONS.md` 按文档性质拆分而来，不改变已接受的 [ADR-011](../decisions/ADR-011-three-node-distributed-deployment.md)、部署拓扑、数据、安全或恢复语义。

## 1. 适用范围与服务目标

- v1.0 生产运行在三台 2 vCPU / 2 GB RAM Linux 云节点上；Mac 是开发机，Windows 是非关键辅助节点；
- 该拓扑提供资源与故障域隔离，不提供多节点高可用、自动故障转移或跨地域灾备；
- 恢复点目标为 `RPO ≤ 24h`，恢复时间目标为 `RTO ≤ 4h`；
- 允许计划内短时维护停机；任一生产云节点故障期间不承诺持续服务；
- Mac 或 Windows 离线不得影响生产 readiness 或核心业务。

## 2. 编排与发布一致性

- 开发与生产必须复用同一 Dockerfile、配置 Schema、健康检查和不可变镜像版本；
- 生产镜像覆盖实际云主机架构；Mac 为 Apple Silicon 时发布流程还必须能产出 `linux/arm64` 开发镜像；
- 生产禁止使用浮动 `latest`、现场修改镜像或从开发机目录挂载生产代码；
- 每份生产 Compose 只声明本机组件，跨主机依赖不得使用 Compose `depends_on` 表达；
- 同一发布批次的三个节点必须使用兼容镜像、配置和 Contract 版本；
- Windows 或 Mac 的在线状态不得进入发布完成判定。

## 3. 网络与信任边界

- 公网暴露、私网访问方向、Internal API 隔离和服务发现必须符合 [ARCHITECTURE.md](ARCHITECTURE.md) §6.3；
- MySQL 使用服务级最小权限账号；Redis 使用认证、独立 DB、显式队列、Key 前缀和 `noeviction`；
- 环境文件和 Secret 权限最小化，日志不得打印配置值；Mac 不保存生产 Secret，Windows 不保存未加密生产数据；
- 三节点使用 UTC 与可靠时间同步；时钟异常必须阻止依赖 Service JWT 或任务租约的节点进入 readiness；
- 私网 DNS 或连接失败时不得回退公网地址或放宽鉴权。

## 4. 健康与告警

- liveness 只验证本进程响应；
- readiness 验证接收业务流量所需的 MySQL、Redis、签名材料、私网依赖和关键存储；
- Knowledge readiness 额外验证 uploads/Chroma 路径与向量存储可初始化；
- Research readiness 验证 Internal Retrieval 私网地址可解析；外部 Provider 只影响 capability 状态，不阻止 API 进程启动；
- Beat 使用调度心跳和最后执行时间判定，Knowledge Beat 与 Research Beat 各只能存在一个实例；
- 告警至少覆盖节点失联、私网 DNS/时间异常、队列积压、租约过期、入库失败、Research 失败、权限拒绝异常上升、磁盘水位、备份失败和 Contract 不兼容；
- 生产告警事实不得只存在于 Windows；Dependency detail 只对内部运维开放。

## 5. 资源与背压

- 云节点 1 的 Research Worker concurrency 为 1；云节点 3 的 Knowledge Worker concurrency 为 1；
- 生产允许两个节点各执行一个重任务，但各自遵守队列长度、用户并发和预算限制；
- 开发单机全栈使用跨服务重任务准入锁，避免文档入库与深度研究同时导致本机 OOM；
- 云节点 2 优先保证 MySQL/Redis，备份不得在业务高峰无上限占用 CPU、内存或磁盘 IO；
- 达到资源上限时排队、拒绝扩大存储的写入或受控停止，不提高 Worker 并发换吞吐；
- 完整 Prometheus/Grafana/Loki 不作为任一 2C2G 节点默认常驻组件。

## 6. 备份与恢复

- 每日主备份必须为 MySQL 三个逻辑数据库与 Knowledge uploads/Chroma 生成统一 `backup_batch_id`；
- 每个批次必须保存三份 Compose 的版本、配置键名清单、镜像版本、迁移 revision、时间点和校验和；
- Redis 不作为业务恢复的唯一事实来源，Redis AOF 不能替代 MySQL 与 Knowledge-owned 持久卷备份；
- Windows 可保存加密异地副本，但不是唯一备份位置；Windows 离线不得导致当日主备份失败；
- 恢复前必须核对 MySQL 与 uploads/Chroma 的 `backup_batch_id`，批次不一致不得直接对外启动；
- 首次三节点上线、存储变更或恢复流程变化后，必须在空环境演练登录、权限、文档检索、单 KB Chat、Research、报告引用和来源二次鉴权；
- 恢复演练必须记录实际 RPO/RTO、失败明细和处置结果。

## 7. 发布与回滚门禁

- 发布前必须完成配置、私网、时间同步、备份和兼容迁移校验；
- 发布后必须执行健康、网络暴露、Contract 和旗舰链路 smoke；
- 应用回滚使用上一不可变镜像；数据库迁移优先使用 expand/contract；
- 不可逆数据变化使用前滚修复或同批次备份恢复，不得声称可直接 downgrade；
- 停止服务默认保留卷，删除卷必须单独授权并明确节点、卷名和恢复影响；
- 回滚后重新验证登录、权限、Chat、Research、SSE、报告引用和 Internal Retrieval。

## 8. 故障语义

| 故障 | 规范行为 |
|:---|:---|
| 云节点 1 不可用 | 公网入口与 Research 不可用；不自动切换到 Windows/Mac |
| 云节点 2 不可用 | API readiness 失败，停止依赖写入和新异步分发；内存或 Redis 不提升为业务事实源 |
| 云节点 3 不可用 | Auth、Knowledge、Internal Retrieval 与依赖身份复核的新 Research 操作失败关闭；hybrid 只按既有完整度语义处理 |
| Windows 或 Mac 不可用 | 核心生产能力不受影响；辅助监控、构建、诊断或异地复制可延迟并告警 |
| Redis 不可用 | 拒绝新异步分发；MySQL 完成事实不回退 |
| Worker 退出 | Knowledge checkpoint 或 Research 租约扫描恢复 |
| Beat 重复实例 | 阻止发布并停止多余实例，核对调度心跳与重复任务 |
| 私网 DNS 或时钟异常 | 受影响节点 readiness 失败，不回退公网地址或放宽 JWT/租约校验 |
| 磁盘保护水位 | 拒绝扩大存储的写入，保留读取、删除和诊断 |
| Contract 不兼容 | 失败关闭，不进入权限或业务处理 |

## 9. 操作审计

备份、恢复、迁移、回滚、密钥轮换、私网或防火墙调整和治理操作必须记录操作者、时间、节点、目标、版本、请求 ID、结果和安全错误摘要；不得记录凭证或正文。

