# M0 Monorepo 迁移验收

验收日期：2026-08-02

## 结论

DocMind 的 Knowledge 后端与 Vue Web、ResearchMind 的 Research 后端已迁入 EvidSight Monorepo。来源提交、迁移历史、服务边界、测试基线、镜像构建和单机 Compose 配置均已验证。本次仅完成结构迁移与单机运行基线，不改变既有 API、权限、状态机或 SSE 行为。

## 固定来源与历史

| 来源 | 固定提交 | 迁入位置 | 导入提交 | 导入前回滚点 |
| --- | --- | --- | --- | --- |
| DocMind backend | `a390a2a83df7d0bd3087bb2df309c26ecf527e08` | `services/knowledge/` | `d3fc139` | `9b195ac` |
| DocMind frontend | `a390a2a83df7d0bd3087bb2df309c26ecf527e08` | `apps/web/` | `885fe92` | `f0691b2` |
| ResearchMind backend | `40f7faa1e951b375c9d7997d3d15ab9406e1e20e` | `services/research/` | `6a5c2ea`, `62c9f28` | `2acdbfd` |

来源 refs 为 `imports/docmind-a390a2a` 与 `imports/researchmind-40f7faa`。Subtree 导入提交保留第二父提交，因此完整来源历史可从 refs 或导入提交的第二父访问。由于 Git `--follow` 不会自动跨越所有 subtree 前缀变化，目标路径的 `git log --follow` 可能只显示迁入后的提交；这不代表来源历史丢失。

## 验证结果

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 仓库结构与 Compose 契约 | `python3.12 -m pytest tests/architecture -v` | PASS，9 passed |
| Knowledge 全量测试 | `services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests` | PASS，1306 passed |
| Research 全量测试 | `TAVILY_API_KEY=test-tavily-key services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests` | PASS，869 passed，1 skipped |
| Web 测试 | `npm --prefix apps/web test` | PASS，30 files，513 passed |
| Web 构建 | `npm --prefix apps/web run build` | PASS |
| 开发 Compose 配置 | `docker compose config --quiet` | PASS |
| 生产资源覆盖配置 | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet` | PASS |
| Knowledge 镜像 | `docker build -t evidsight/knowledge:migration services/knowledge` | PASS，`sha256:63a4d088df15...` |
| Research 镜像 | `docker build -t evidsight/research:migration services/research` | PASS，`sha256:fec7a8f5112d...` |
| 生产 Compose 运行态 | `bash scripts/smoke_compose.sh --production` | PASS，8 个容器启动；两个 API 健康检查通过；Internal Retrieval 返回 `404` |

Knowledge 测试使用隔离 MySQL：`127.0.0.1:3307`，数据库 `docmind`；这是本机原生 MySQL 仍占用宿主机 `3306` 时的测试隔离，不改变 Compose 内部标准 MySQL 端口 `3306`。Research 测试中的 Tavily 值是测试占位符，测试不会以该值调用真实服务。

## 数据库迁移链

- Knowledge：16 个迁移文件，head `a7b8c9d0e1f2`。
- Research：11 个迁移文件，静态迁移链 head `11eb68567494`。
- 本阶段保留两条服务既有迁移链；不创建 `platform_db` 统一迁移链，也不执行生产数据迁移。

## 单机部署边界

- 开发 Compose 不设置容器内存上限，适合本地 Docker Desktop 动态使用资源。
- `docker-compose.prod.yml` 按 2C2G 单机环境设置生产资源上限。
- MySQL 只在 Compose 网络内使用 `3306`，未映射宿主机端口；Redis 同样只供服务网络访问。
- Nginx 暴露统一入口：Knowledge `/api/*`，Research `/api/research/*`；Internal Retrieval 路由在 M0 应返回 `404`。
- 验收结束后已执行 `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`；容器和网络已移除，数据卷保留。

## 明确不在 M0 范围内

- 统一身份与跨服务授权。
- Internal Retrieval 实现。
- Research 前端并入唯一 Web。
- `platform_db`、生产数据迁移和生产流量切换。
- External OpenAPI/内部契约生成物与 v1.0 发布验收。

## 回滚

结构迁移可按上表的“导入前回滚点”逐单元回退；不得删除来源 refs。生产数据未在本次验收中迁移，因此不存在需要反向执行的数据回滚。
