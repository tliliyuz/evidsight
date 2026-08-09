# TEST EXECUTION — 测试执行与发布记录指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 操作指南 |
| 最后更新 | 2026-08-09 |

> 本文说明如何执行测试和记录结果。必须覆盖的环境、场景、阈值和发布门禁以 [测试与发布验证规范](../specs/TESTING.md) 为唯一权威来源。

## 1. Monorepo 基线命令

```bash
uvx ruff check services/ scripts/ tests/ packages/contracts/
uvx ruff format --check services/ scripts/ tests/ packages/contracts/
bash scripts/check_python_types.sh
python3.12 -m pytest tests/architecture -v
uv run --project services/knowledge pytest
uv run --project services/research pytest
pnpm --dir apps/web run lint
pnpm --dir apps/web run format:check
pnpm --dir apps/web test
pnpm --dir apps/web run build
docker compose config --quiet
```

命令必须在当前候选提交上执行。任何失败、跳过或环境缺失都必须如实记录，不能折算为通过。

### 1.1 基础 CI 执行编排

基础 CI 的覆盖范围和不纳入项以 [TESTING.md §2.1](../specs/TESTING.md#21-自动化门禁分层) 为准。`.github/workflows/ci.yml` 已拆分为可并行且结果独立的 required checks：

| Check | 执行内容 | 环境约束 |
|:---|:---|:---|
| `python-quality` | Ruff check/format check、Python 全量 mypy | Python 3.12；根锁文件与两服务固定 `.venv`；不临时安装依赖 |
| `backend-fast-unit` | 明确登记的纯单元测试 | 不连接 MySQL/Redis/Celery/Chroma/外部 Provider |
| `contracts` | Schema、Fixture、已登记生成物差异、Consumer、Provider、兼容与静态扫描 | Provider 使用受管服务容器，不启动数据服务 |
| `architecture-compose` | 根 Architecture tests、开发 Compose `config --quiet` | 只解析配置，不启动全栈 |
| `openapi` | 语法、`$ref`、示例、路由/测试覆盖一致性、基线合并后的 Breaking Change | 使用受保护分支基线；不启动 API 依赖 |
| `web` | 冻结安装、ESLint、Prettier check、Vitest、TypeScript、Vite build | 只使用 `pnpm-lock.yaml`；不改写源码 |

当前 `apps/web` 的 `build` 已内含 `tsc --noEmit`。在独立 `type-check` 脚本落地前，`web` check 通过 `build` 覆盖类型检查，不重复执行同一条 `tsc` 命令。

每个 check 均使用 fail-fast 退出码报告结果，不执行 `--fix`、`--write`、生成物回写、Git 写操作或远端发布。同一 PR 的新提交可取消已过时运行；取消不记为通过。

本地复现新增门禁使用以下只读入口：

```bash
make fast-unit
make contracts-ci
make openapi-ci
```

`contracts-ci` 和 `openapi-ci` 只构建 Knowledge Dockerfile 的 `ci-test` 测试 stage；该 stage 使用带哈希的 `requirements-dev.lock`，不启动数据服务，也不改变生产 `runtime` stage。受保护分支是否强制这六个 check，仍须在 GitHub 仓库规则中以同名 job 配置 required status checks。

## 2. M5 部署与集成验收

M5 在基础 CI 之上增加镜像构建与缓存、开发 Compose 全栈集成、MySQL Alembic `upgrade/downgrade/upgrade`、Knowledge/Research Worker 与 SSE、跨服务 Provider/Consumer、镜像安全检查、staging 部署，以及备份、恢复、回滚和故障演练。仓库源码的轻量凭证泄漏扫描不依赖镜像，可在基础 CI 阶段先行引入；镜像内容与镜像漏洞检查仍属 M5。

真实大模型、外部搜索调用和评估集不进入每个 PR 的必过门禁；只在冻结数据集、明确预算、可归档环境和可重复记录的候选验收中执行。

### 2.1 三节点 Compose 配置检查

M5 三节点 Compose 资产落地后执行：

```bash
docker compose -f deploy/compose/cloud-edge.yml config --quiet
docker compose -f deploy/compose/cloud-data.yml config --quiet
docker compose -f deploy/compose/cloud-knowledge.yml config --quiet
```

随后执行三份配置联合静态检查，并在实际环境验证公网暴露、私网 DNS、节点中断、Beat 单实例和跨节点恢复。单独 `config --quiet` 通过不能替代这些验证。

## 3. 提交前静态门禁

每个 worktree 首次使用时安装 hook：

```bash
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type commit-msg
```

全仓静态基线：

```bash
.venv/bin/pre-commit run --all-files
```

日常提交由 hook 对暂存文件执行；hook 失败不得绕过后声称门禁通过。

mypy 必须通过 `scripts/check_python_types.sh` 分别调用两个服务虚拟环境；首次准备环境时执行：

```bash
uv pip install --python services/knowledge/.venv/bin/python -r services/knowledge/requirements-dev.txt
uv pip install --python services/research/.venv/bin/python -r services/research/requirements-dev.txt
```

不得从根 `.venv` 偶然解析任一服务依赖，也不得把 mypy 加入生产镜像使用的 `requirements.txt`。

## 4. 发布记录模板

```text
候选版本/提交：
环境与资源：
数据集版本：
执行命令：
通过/失败/跳过：
已知偏差与批准人：
证据链接：
```

原 `docs/migration/` 过程记录已由负责人于 2026-08-02 主动删除，不再作为 M0 或 M1 门禁。后续候选版本的实际验证结果使用本模板记录在对应评审或发布记录中；M6 发布验收单独建立带日期的候选版本记录。
