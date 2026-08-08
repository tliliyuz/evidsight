# TEST EXECUTION — 测试执行与发布记录指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 操作指南 |
| 最后更新 | 2026-08-08 |

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

## 2. 三节点 Compose 配置检查

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
