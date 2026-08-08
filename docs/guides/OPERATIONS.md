# OPERATIONS — 三节点部署与运维操作指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 操作指南 |
| 最后更新 | 2026-08-08 |

> 本文说明如何执行三节点部署、启动、备份、恢复、发布和故障处置，不定义新的系统行为。节点职责与网络边界见 [总体架构](../specs/ARCHITECTURE.md)，必须达到的可靠性结果见 [运行可靠性与恢复规范](../specs/RELIABILITY.md)。

## 1. 编排入口

| 入口 | 使用位置 | 组件 |
|:---|:---|:---|
| 根 `docker-compose.yml` | Mac 等开发机 | 完整本地开发栈 |
| `deploy/compose/cloud-edge.yml` | 云节点 1 | Nginx、Web、Research API/Worker/Beat |
| `deploy/compose/cloud-data.yml` | 云节点 2 | MySQL、Redis、主备份调度 |
| `deploy/compose/cloud-knowledge.yml` | 云节点 3 | Knowledge API/Worker/Beat、uploads、Chroma |

三份生产 Compose 是 M5 待实现资产。文件不存在或未完成验收时，只能执行根 Compose 的本地开发流程，不得按本文声称生产部署已完成。

## 2. 部署前检查

1. 确认三台云节点的规格、磁盘、UTC 时间同步和 Docker Compose 版本；
2. 确认 VPC 或加密覆盖网络连通，私网 DNS 可解析；
3. 确认公网只计划开放云节点 1 的 `80/443`；
4. 确认三个节点使用同一候选版本的不可变镜像；
5. 分别执行配置 smoke，检查节点最小 Secret 集合和生产安全默认值；
6. 检查 Knowledge/Research Beat 均只有一个计划实例；
7. 首次部署前准备空环境恢复演练和回滚窗口。

## 3. 启动流程

1. 启动云节点 2 的 MySQL、Redis 和持久卷，等待健康；
2. 执行 platform、knowledge、research 三条数据库迁移链；
3. 启动云节点 3 的 Knowledge API，等待 readiness；
4. 启动云节点 3 的 Knowledge Worker 与 Knowledge Beat；
5. 启动云节点 1 的 Research API，等待 readiness；
6. 启动云节点 1 的 Research Worker 与 Research Beat；
7. 启动云节点 1 的 Web 与 Nginx；
8. 执行节点健康、网络边界、Contract 和旗舰链路 smoke。

跨节点依赖以 readiness 和有限重试判断，不能用容器进程存在代替服务可用。

## 4. 日常检查

- 查看三节点 liveness、readiness、Beat 心跳和镜像版本；
- 查看队列深度、租约过期、入库失败、Research 失败和磁盘水位；
- 检查私网 DNS、节点时间偏差与数据库连接池；
- 检查最近主备份的 `backup_batch_id`、两侧校验和与异地复制状态；
- Windows 监控副本离线时记录辅助能力降级，不把生产判定迁移到 Windows。

## 5. 备份流程

1. 生成唯一 `backup_batch_id`；
2. 在云节点 2 备份三个逻辑数据库；
3. 在云节点 3 对 uploads 与 Chroma 创建同批次快照；
4. 收集 Compose 版本、配置键名、镜像、迁移 revision、时间点和校验和；
5. 校验主备份完整性并写入操作记录；
6. 主备份成功后，可将加密副本复制到 Windows；复制失败只影响异地副本状态并触发告警。

## 6. 恢复演练

1. 选择同一 `backup_batch_id` 的 MySQL 与 Knowledge 持久数据；
2. 在空环境恢复云节点 2 与云节点 3 数据；
3. 校验 migration revision、文件数量、向量索引和校验和；
4. 按第 3 节顺序启动三节点；
5. 验证登录、权限、文档检索、单 KB Chat、三类 Research、报告引用和来源二次鉴权；
6. 记录实际 RPO/RTO、偏差、处置和批准人。

批次不一致、权限异常或引用闭包失败时停止恢复，不得对外启动。

## 7. 发布与回滚流程

发布：

1. 校验配置、私网、时间同步和恢复点；
2. 执行向后兼容的数据库迁移；
3. 更新云节点 3 的 Knowledge Worker、Beat 与 API；
4. 更新云节点 1 的 Research Worker、Beat 与 API；
5. 更新云节点 1 的 Web 与 Nginx；
6. 执行健康、暴露面、Contract 和旗舰链路 smoke。

回滚：

1. 停止继续发布并保留全部卷；
2. 按兼容顺序切回上一不可变镜像；
3. 不可逆数据变化选择前滚修复或同批次备份恢复；
4. 重新执行登录、权限、Chat、Research、SSE、报告和 Internal Retrieval smoke；
5. 记录失败原因、影响窗口和最终状态。

## 8. 节点故障处置

- 云节点 1：确认公网入口与 Research 中断，不切换到 Windows/Mac；恢复后检查 SSE、队列和 Beat 单实例；
- 云节点 2：阻止新写入和任务分发，检查 MySQL/Redis 数据与磁盘，不以 Redis 或 Worker 内存恢复业务事实；
- 云节点 3：保持 Auth、Knowledge 和 Internal Retrieval 失败关闭，恢复后检查 uploads/Chroma parity 与权限；
- 私网 DNS/时钟：使受影响节点保持未就绪，修复基础设施后重新验证 JWT、租约和跨服务调用；
- Beat 重复：停止多余实例，检查重复调度、租约与任务终态，再恢复单实例运行。

故障的对外行为必须以 [RELIABILITY.md](../specs/RELIABILITY.md) §8 为准；本节只说明操作顺序。
