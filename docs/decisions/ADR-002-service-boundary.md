# ADR-002：双服务数据所有权与 Internal Retrieval 边界

- 状态：accepted
- 日期：2026-08-01

## 背景

EvidSight 由 Knowledge 与 Research 两个来源项目演进而来。直接共享数据库、ORM、Chroma 或上传目录会使权限、迁移和发布无法独立验证。

## 决策

- Knowledge 拥有 `platform_db`、`knowledge_db`、上传文件和向量索引。
- Research 只拥有 `research_db`，不连接 Knowledge 数据库和存储。
- Research 使用服务身份、Platform User ID 和版本化 Contract 调用 `/internal/v1`。
- Knowledge 在每次内部检索时重新计算用户状态和全部 KB READ 权限。
- 跨数据库 ID 不建立外键；通过稳定 UUID、Contract、应用校验和审计保证一致性。

## 后果

服务可以独立迁移、测试和部署，但需要 Provider/Consumer 契约测试和明确的失败恢复。跨服务同步查询增加网络成本，不允许以共享数据库绕过。

## 被否决方案

- 两个服务共享 ORM 和数据库账号：迁移、权限和发布无法独立验证。
- Research 直接挂载 Chroma/上传卷：绕过 Knowledge 授权与数据生命周期。
- M0 立即合并为单体：同时改变来源行为和数据所有权，无法证明迁移等价。

## 重新评估触发条件

只有在独立 Identity Service 或新的受审查服务边界获批后，才改变身份归属或内部调用方式。

## 相关规范

- [总体架构](../specs/ARCHITECTURE.md)
- [身份与访问](../specs/IDENTITY_AND_ACCESS.md)
- [跨服务契约](../../packages/contracts/README.md)
