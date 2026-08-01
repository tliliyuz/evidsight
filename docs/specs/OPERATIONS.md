# OPERATIONS — 部署与运维指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 运维基线 |
| 最后更新 | 2026-08-01 |

## 1. 基线

v1.0 面向单机 Docker Compose、2 vCPU / 2 GB RAM 试点。默认核心组件为 Nginx、Web、Knowledge API/Worker、Research API/Worker/Beat、MySQL、Redis 和 Knowledge 向量存储。完整 Prometheus/Grafana 不默认常驻。

## 2. 网络与权限

- 对外只暴露 Nginx；
- `/internal/v1/*`、`/metrics`、MySQL、Redis、Chroma 和 Worker 不对外暴露；
- 服务使用独立数据库账号、Redis DB、队列和 Key 前缀；
- 环境文件权限最小化，日志不得打印配置值。

## 3. 启动顺序

1. 配置验证；
2. MySQL、Redis 和持久卷；
3. 两个服务数据库迁移；
4. Knowledge API/Worker；
5. Research API/Worker/Beat；
6. Web 与 Nginx；
7. readiness、Contract smoke 和旗舰链路 smoke。

外部 Provider 不阻止 API 进程启动，但相应能力必须显示不可用。

## 4. 健康与告警

- liveness 只验证进程响应；
- readiness 验证接收业务流量所需的数据库、Redis、签名材料和关键存储；
- 告警至少覆盖队列积压、租约过期、入库失败、Research 失败、权限拒绝异常上升、磁盘水位、备份失败和 Contract 不兼容；
- Dependency detail 只对内部运维开放。

## 5. 备份与恢复

每日备份三个逻辑数据库，并对 Knowledge uploads 与 Chroma 做同批次快照；同时保存配置键名清单、镜像版本、迁移 revision 和校验和。Redis 不替代业务备份。

目标：`RPO ≤ 24h`、`RTO ≤ 4h`。首次上线、存储变更和恢复流程变化后必须在空环境演练，验证登录、权限、文档检索、单 KB Chat、Research、报告引用和来源二次鉴权。

## 6. 发布与回滚

- 镜像使用不可变标签；
- 先配置/备份，再 expand 迁移，再 Worker/API/Web；
- 发布后执行健康、契约和旗舰链路 smoke；
- 应用回滚使用上一镜像；不可逆数据变化使用前滚修复或备份恢复；
- 停止服务默认保留卷，删除卷必须单独授权并明确目标。

## 7. 常见故障语义

| 故障 | 处理 |
|:---|:---|
| MySQL 不可用 | readiness 失败，停止依赖写入的流量 |
| Redis 不可用 | 拒绝新异步分发；MySQL 完成事实不回退 |
| Knowledge 不可用 | knowledge Research 失败；hybrid 仅按完整度部分完成 |
| Web Provider 不可用 | web Research 失败；hybrid 仅按完整度部分完成 |
| Worker 退出 | Knowledge checkpoint 或 Research 租约扫描恢复 |
| 磁盘保护水位 | 拒绝扩大存储的写入，保留读取、删除和诊断 |
| Contract 不兼容 | 失败关闭，不进入权限或业务处理 |

## 8. 操作记录

备份、恢复、迁移、回滚、密钥轮换和治理操作必须记录操作者、时间、目标、版本、请求 ID、结果和安全错误摘要；不得记录凭证或正文。
