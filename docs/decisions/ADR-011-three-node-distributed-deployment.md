# ADR-011：三节点云端分布式部署与本地全栈开发并存

- 状态：accepted
- 日期：2026-08-08
- 里程碑：M5
- 命中的 ADR 检查项：2、4、5、7
- 接受：负责人 2026-08-08 明确裁决「接受 ADR-011」

## 背景

v1.0 当前部署基线是一台 2 vCPU / 2 GB RAM Linux 主机上的单机 Docker Compose。该基线通过低并发、显式队列和本地持久卷控制资源占用，但 API、Worker、MySQL、Redis 与 Knowledge 本地存储共享同一故障域和内存预算。

当前可用资源调整为三台稳定的 2 vCPU / 2 GB RAM 云服务器、一台 Windows 主机和一台稳定性不足的 Mac。生产部署需要利用三台云服务器隔离边缘入口、数据基础设施与 Knowledge 数据岛，同时满足以下约束：

- Mac 继续支持一条命令启动完整本地开发环境，但不成为生产依赖；
- Windows 可承担辅助能力，但其关机或网络中断不得影响线上核心链路；
- Knowledge API、Knowledge Worker、uploads 与嵌入式 Chroma 必须保持同机，避免把本地持久目录当作跨主机共享存储；
- MySQL、Redis、Internal API 与运维端点不得暴露公网；
- 多主机部署不改变外部 API、Internal Retrieval、Evidence Contract、身份权限或数据所有权语义；
- v1.0 不因多主机落位而宣称具备多节点高可用或自动故障转移。

该选择改变生产部署拓扑和网络信任边界，调整跨节点备份恢复策略，并在多种基础设施方案中形成长期部署约束；同时需要同步总体架构、运维、配置和测试规范。因此命中 ADR 检查项 2（系统边界）、4（数据与安全）、5（核心机制）和 7（跨规范影响）。

## 决策

### 开发与生产采用两种编排模式

- 根 `docker-compose.yml` 保留为开发机单机全栈入口；Mac 可在本地启动 Nginx/Web、两个 API、两个 Worker、两个 Beat、MySQL、Redis、uploads 与 Chroma，不依赖任何生产节点。
- 生产部署按节点提供独立 Compose 入口；各节点只声明本机进程，不使用 Compose `depends_on` 表达跨主机依赖。
- 开发与生产复用同一 Dockerfile、版本化镜像、配置 Schema 和健康检查；环境差异只由未提交配置、Secret、连接地址和服务落位表达，生产拓扑不得进入业务代码条件分支。
- 开发数据卷、生产数据卷和密钥材料完全隔离，禁止开发环境连接生产数据库、Redis 或 Knowledge 持久目录。

### 三台云服务器按服务数据岛落位

| 节点 | 唯一生产职责 | 持久数据 |
|:---|:---|:---|
| 云节点 1：Edge / Research | Nginx、Web 静态资源、Research API、Research Worker、Research Beat | Research Beat 调度状态；普通业务事实仍写 MySQL |
| 云节点 2：Data | MySQL、Redis、主备份调度 | 三个逻辑数据库、Redis AOF、备份元数据 |
| 云节点 3：Knowledge | Knowledge API、Knowledge Worker、Knowledge Beat | uploads、Chroma、Knowledge Beat 调度状态 |

- Knowledge API、Worker 与 Knowledge-owned 持久卷不得跨节点拆开；Research Service 不挂载或直读这些卷。
- Research Beat 与 Knowledge Beat 各保持单实例；不得因节点拆分重复启动调度实例。
- Windows 仅作为监控、日志汇总、镜像构建、人工启用的诊断节点或加密备份副本目标，不承担唯一 API、Worker、数据库、Broker、调度或存储职责。
- Mac 仅作为开发节点，不加入生产私网访问白名单，不保存生产 Secret 或生产数据副本。

### 私网是唯一服务间传输面

- 只有云节点 1 的 Nginx 对外开放 `80/443`；生产必须启用 TLS。
- 三台云服务器优先使用云厂商 VPC 私网；无法共享 VPC 时使用受控加密覆盖网络。禁止通过公网安全组直接开放 MySQL、Redis、Knowledge API、Internal API、metrics 或管理端口。
- Nginx 通过私网代理 Knowledge 与 Research 的外部 API；`/internal/v1/*` 不得配置为 Nginx 外部路由。
- MySQL 与 Redis 仅允许云节点 1、云节点 3 的已登记私网身份访问；按服务使用独立最小权限账号、Redis DB、队列和 Key 前缀。
- 生产服务通过稳定私网 DNS 名称发现，不硬编码容器 IP、公网 IP 或开发 Compose 服务名。
- 三节点必须使用 UTC 和可靠时间同步；时钟异常必须阻止依赖短时 Service JWT 或任务租约的节点进入 readiness。

### 镜像、发布与跨节点启动

- 生产使用同一发布批次的不可变镜像标签；镜像至少覆盖实际云主机架构，开发所需时同时提供 `linux/amd64` 与 `linux/arm64`。
- 发布顺序为配置验证和备份、Data 节点与迁移、Knowledge 节点、Research 节点、Nginx 对外就绪；回滚按兼容顺序逆向执行。
- 跨节点依赖由 readiness、有限重试和发布编排验证，不以容器已启动等价替代依赖可用。
- Windows 或 Mac 的在线状态不得进入生产 readiness 判定。

### 备份与恢复保持跨数据域一致

- MySQL 三个逻辑数据库与云节点 3 的 uploads/Chroma 必须生成同一备份批次标识，并记录镜像版本、迁移 revision、时间点和校验和。
- Redis 不作为业务恢复的唯一事实来源；Redis AOF 不能替代 MySQL 与 Knowledge-owned 持久卷备份。
- Windows 可保存加密的异地备份副本，但不是唯一备份位置；Windows 离线不得使当日主备份失败。
- 首次启用三节点拓扑、存储位置变化或恢复流程变化后，必须在空环境执行跨节点恢复演练并验证登录、权限、文档检索、Chat、Research、报告引用和内部证据二次鉴权。

### 故障语义与能力边界

- 云节点 1 不可用：统一公网入口与 Research 能力不可用，不发生自动故障转移。
- 云节点 2 不可用：依赖 MySQL/Redis 的 API readiness 失败，停止新写入和异步分发，不把缓存或 Worker 内存提升为事实源。
- 云节点 3 不可用：认证入口、Knowledge、Internal Retrieval 与依赖内部身份复核的新 Research 操作失败关闭；既有规范允许的 hybrid 降级语义保持不变。
- Windows 或 Mac 不可用：线上核心能力不受影响；监控副本、构建、诊断或异地备份复制可延迟并告警。
- 该拓扑只提供资源隔离和故障域分离，不提供数据库、Broker、API 或存储的高可用承诺。

## 后果

- 三台 2C2G 云服务器分别承载 Research、数据基础设施和 Knowledge 重负载，减少单机内存竞争。
- Knowledge 本地文件与嵌入式向量存储保持封装，不引入不安全的跨主机共享目录。
- Mac 保留完整、离线可用的全栈开发体验，同时其稳定性不再影响生产。
- 生产发布、诊断、备份与恢复从单机操作扩展为跨节点协调，运维复杂度和网络依赖增加。
- 当前单实例数据库、Broker、API 与本地向量存储仍是单点；若需要高可用，必须重新执行 ADR 检查并补充专门设计。

## 被否决方案

### 将 Mac 纳入生产 Knowledge 节点

Mac 已知稳定性不足，且 Docker Desktop、休眠、家庭网络与人工使用会扩大生产故障面。否决。

### 将 Windows 作为唯一 Research Worker

Windows 关机、更新或 Docker Desktop 中断会让全部研究任务停止消费，使非云主机成为生产关键依赖。否决；仅保留非关键辅助职责。

### 将 Knowledge API 与 Worker 分到不同主机并共享 Chroma 目录

当前 uploads 与嵌入式 Chroma 依赖 Knowledge-owned 本地卷；通过 SMB/NFS 等共享目录不能自动获得受支持的并发写入、一致快照和故障恢复语义。否决。未来若迁移到对象存储与网络化向量服务，需重新执行 ADR 检查。

### 直接引入 Kubernetes 或 Docker Swarm

三台 2C2G 节点资源有限，当前无多实例存储、自动故障转移或弹性调度需求；引入集群控制面不能解决嵌入式 Chroma 与单实例数据库的状态问题，反而扩大 M5 运维范围。v1.0 否决。

### 只保留一台 2C2G 生产主机，其余节点冷备

该方案运维简单，但不能解除当前 Worker、数据库和 API 的内存竞争，也不利用已有稳定云节点进行故障域隔离。作为紧急回滚拓扑保留，不作为目标部署。

## 验收条件

1. Mac 在不连接生产网络的情况下通过根 Compose 启动完整开发栈，并完成配置与旗舰链路 smoke。
2. 三份生产节点 Compose 分别通过配置校验，合并后的服务清单没有缺失组件或重复 Beat。
3. 公网扫描只能访问云节点 1 的 `80/443`；MySQL、Redis、Knowledge API、Internal API 与 metrics 公网不可达。
4. 云节点 1、云节点 3 通过私网连接云节点 2；Research 通过私网直达 Knowledge Internal API，且服务认证与用户实时授权保持有效。
5. 任一云节点中断时表现符合本 ADR 的故障语义；Mac/Windows 中断不影响线上核心能力。
6. 同一备份批次可在空环境恢复 MySQL、uploads 与 Chroma，并在 `RTO ≤ 4h`、`RPO ≤ 24h` 内通过恢复验证。
7. 同一发布版本的镜像可在目标云节点与 Mac 开发环境运行，不依赖现场修改镜像内容。

## 重新评估触发条件

- 需要数据库、Redis、API、Worker 或 Knowledge 存储的自动故障转移；
- Knowledge uploads 迁移到对象存储，或 Chroma 替换为支持远程多实例访问的向量服务；
- Research Worker 并发或跨节点水平扩展基线改变；
- 三台云服务器无法使用受控私网，必须经过公网通信；
- 试点规模、队列等待或资源峰值超过三节点 2C2G 容量；
- 引入 Kubernetes、Swarm 或其他集群编排平台。

## 与既有 ADR 的关系

- 不推翻既有 accepted ADR。
- 保持 [ADR-002](ADR-002-service-boundary.md) 的双服务数据所有权和 Internal Retrieval 边界。
- 保持 [ADR-005](ADR-005-unified-identity-service-auth-egress.md) 的统一身份、服务认证与失败关闭语义。
- 保持 [ADR-007](ADR-007-knowledge-document-lifecycle-delete-consistency.md) 的 Knowledge 文件、版本和删除一致性。
- 保持 [ADR-008](ADR-008-research-task-lifecycle-recovery.md) 的单调租约、恢复扫描和迟到提交拒绝语义。

## 相关规范

- [总体架构](../specs/ARCHITECTURE.md) §6、§11、§13—§16
- [运行可靠性与恢复规范](../specs/RELIABILITY.md)
- [运维操作指南](../guides/OPERATIONS.md)
- [配置规范](../specs/CONFIGURATION.md)
- [测试规范](../specs/TESTING.md)
- [开发指南](../guides/DEVELOPMENT.md)
