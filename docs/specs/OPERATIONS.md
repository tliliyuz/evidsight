# OPERATIONS — 部署与运维指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 运维基线 |
| 最后更新 | 2026-08-08 |

## 1. 基线

v1.0 生产环境按 [ADR-011](../decisions/ADR-011-three-node-distributed-deployment.md) 使用三台 Linux 云服务器，每台 2 vCPU / 2 GB RAM：

- 云节点 1（Edge / Research）：Nginx、Web、Research API、Research Worker、Research Beat；
- 云节点 2（Data）：MySQL、Redis、主备份调度；
- 云节点 3（Knowledge）：Knowledge API、Knowledge Worker、Knowledge Beat、uploads、Chroma。

根 `docker-compose.yml` 保留为 Mac 等开发机的单机全栈入口。Windows 只承担非关键监控、构建、诊断或加密备份副本职责；Mac 只承担开发职责。两者离线不得影响生产 readiness 或核心业务。

该拓扑提供资源与故障域隔离，不提供多节点高可用、自动故障转移或跨地域灾备。完整 Prometheus/Grafana/Loki 不默认常驻。

## 2. 编排与镜像

- 开发使用根 `docker-compose.yml`，在不连接生产网络的情况下启动完整栈；
- 生产分别使用 `deploy/compose/cloud-edge.yml`、`cloud-data.yml` 和 `cloud-knowledge.yml`；
- 每份生产 Compose 只声明本机组件，不使用 `depends_on` 表达跨主机依赖；
- 开发与生产复用同一 Dockerfile、配置 Schema、健康检查和不可变镜像版本；
- 生产镜像覆盖实际云主机架构；Mac 为 Apple Silicon 时同时发布 `linux/amd64` 与 `linux/arm64`；
- 生产禁止使用浮动 `latest`、现场修改镜像或从开发机目录挂载生产代码。

生产 Compose 资产尚未落地或未通过 M5 验收时，三节点拓扑状态只能声明为 `specified`，不得声明为已部署或已验证。

## 3. 网络与权限

- 只有云节点 1 的 Nginx 对公网开放 `80/443`，生产必须使用 TLS；
- 三台云节点优先使用同一 VPC；无法共享 VPC 时使用受控加密覆盖网络；
- `/internal/v1/*`、`/metrics`、MySQL、Redis、Chroma、Worker 和 Beat 不对公网开放；
- 云节点 2 的 MySQL/Redis 只允许云节点 1、云节点 3 的已登记私网身份访问；
- 云节点 3 的 Knowledge API 只允许云节点 1 通过私网访问；Nginx 只代理其外部 API，不代理 `/internal/v1/*`；
- 服务使用稳定私网 DNS，不硬编码容器 IP、公网 IP 或开发 Compose 服务名；
- MySQL 使用服务级最小权限账号；Redis 使用独立 DB、显式队列、Key 前缀和认证，并保持 `noeviction`；
- 环境文件和 Secret 权限最小化，日志不得打印配置值；Mac 不保存生产 Secret，Windows 不保存未加密生产数据；
- 三节点使用 UTC 与可靠时间同步；时钟异常阻止依赖 Service JWT 或任务租约的节点进入 readiness。

## 4. 启动顺序

1. 校验三个节点的配置、镜像版本、私网 DNS、时间同步和防火墙；
2. 启动云节点 2 的 MySQL、Redis 和持久卷；
3. 执行 platform、knowledge、research 三条数据库迁移链；
4. 启动云节点 3 的 Knowledge API，等待 readiness；
5. 启动云节点 3 的 Knowledge Worker 与唯一 Knowledge Beat；
6. 启动云节点 1 的 Research API，等待 readiness；
7. 启动云节点 1 的 Research Worker 与唯一 Research Beat；
8. 启动云节点 1 的 Web 与 Nginx；
9. 执行节点健康、网络边界、Contract 和旗舰链路 smoke。

外部 Provider 不阻止 API 进程启动，但相应能力必须显示不可用。跨主机依赖由 readiness 和有限重试判断，不以容器进程存在代替依赖可用。

## 5. 健康与告警

- liveness 只验证本进程响应；
- readiness 验证接收业务流量所需的 MySQL、Redis、签名材料、私网依赖和关键存储；
- Knowledge readiness 额外验证 uploads/Chroma 路径与向量存储可初始化；
- Research readiness 验证 Internal Retrieval 私网地址可解析，但外部 Provider 只影响 capability 状态；
- Beat 使用调度心跳和最后执行时间判定，且每类 Beat 只能存在一个实例；
- 告警至少覆盖节点失联、私网 DNS/时间同步异常、队列积压、租约过期、入库失败、Research 失败、权限拒绝异常上升、磁盘水位、备份失败和 Contract 不兼容；
- Windows 上的监控副本可以延迟，但生产告警事实不得只存在于 Windows；
- Dependency detail 只对内部运维开放。

## 6. 资源与背压

- 云节点 1 的 Research Worker concurrency 为 1；云节点 3 的 Knowledge Worker concurrency 为 1；
- 生产允许两个节点各执行一个重任务，但各自遵守队列长度、用户并发和预算限制；
- 开发单机全栈继续使用跨服务重任务准入锁，避免文档入库与深度研究同时导致本机 OOM；
- 云节点 2 优先保证 MySQL/Redis，备份不得在业务高峰无上限占用 CPU、内存或磁盘 IO；
- 达到资源上限时排队、拒绝扩大存储的写入或受控停止，不提高 Worker 并发换吞吐。

## 7. 备份与恢复

每日备份必须形成统一 `backup_batch_id`：

1. 云节点 2 备份三个逻辑数据库；
2. 云节点 3 对 Knowledge uploads 与 Chroma 创建同批次快照；
3. 保存三份 Compose 的版本、配置键名清单、镜像版本、迁移 revision、时间点和校验和；
4. 主备份完成并校验后，可把加密副本复制到 Windows；Windows 离线不得导致主备份失败。

Redis 不替代业务备份。目标保持 `RPO ≤ 24h`、`RTO ≤ 4h`。首次三节点上线、存储变更和恢复流程变化后，必须在空环境演练，验证登录、权限、文档检索、单 KB Chat、Research、报告引用和来源二次鉴权。

恢复时先核对 MySQL 与 uploads/Chroma 的 `backup_batch_id`；批次不一致不得直接对外启动。恢复顺序与正常启动顺序一致，并记录实际 RPO/RTO。

## 8. 发布与回滚

- 发布前校验配置、私网、时间和备份，再执行 expand 迁移；
- 使用同一候选版本依次更新云节点 3 Knowledge、云节点 1 Research、Web 与 Nginx；
- 发布后执行健康、网络暴露、契约和旗舰链路 smoke；
- 应用回滚使用上一不可变镜像；不可逆数据变化使用前滚修复或同批次备份恢复；
- 停止服务默认保留卷，删除卷必须单独授权并明确节点、卷名和恢复影响；
- Windows/Mac 不参与发布完成判定。

## 9. 常见故障语义

| 故障 | 处理 |
|:---|:---|
| 云节点 1 不可用 | 公网入口与 Research 不可用；不自动切换到 Windows/Mac |
| 云节点 2 不可用 | API readiness 失败，停止依赖写入和新异步分发；内存或 Redis 不提升为业务事实源 |
| 云节点 3 不可用 | Auth、Knowledge、Internal Retrieval 与依赖身份复核的新 Research 操作失败关闭；hybrid 只按既有完整度语义处理 |
| Windows 或 Mac 不可用 | 核心生产能力不受影响；辅助监控、构建、诊断或异地复制延迟并告警 |
| Redis 不可用 | 拒绝新异步分发；MySQL 完成事实不回退 |
| Worker 退出 | Knowledge checkpoint 或 Research 租约扫描恢复 |
| Beat 重复实例 | 阻止发布并停止多余实例，核对调度心跳与重复任务 |
| 私网 DNS 或时钟异常 | 受影响节点 readiness 失败；不得回退公网地址或放宽 JWT/租约校验 |
| 磁盘保护水位 | 拒绝扩大存储的写入，保留读取、删除和诊断 |
| Contract 不兼容 | 失败关闭，不进入权限或业务处理 |

## 10. 操作记录

备份、恢复、迁移、回滚、密钥轮换、私网或防火墙调整和治理操作必须记录操作者、时间、节点、目标、版本、请求 ID、结果和安全错误摘要；不得记录凭证或正文。
