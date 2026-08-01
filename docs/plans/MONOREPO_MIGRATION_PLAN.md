# EvidSight Monorepo 迁移实施计划

> **面向 Agent 执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 子技能，逐个任务执行本计划。步骤使用复选框（`- [ ]`）跟踪状态。

**目标：** 将 DocMind 与 ResearchMind 按已确认的双服务边界迁入 EvidSight Monorepo，在不改变业务行为的前提下形成可独立测试、统一构建和可验证单机编排的代码布局基线。本计划是第一阶段结构迁移，不代表 EvidSight v1.0 整体交付完成。

**架构：** 使用非压缩 Git subtree 保留来源历史：DocMind 的 `backend/` 与 `frontend/` 分别导入 `services/knowledge/` 和 `apps/web/`；ResearchMind 固定提交整体导入临时前缀后，以可审查的 `git mv` 整形到 `services/research/`，研究前端保留为后续统一前端迁移输入。两个 Python 服务继续作为独立依赖、配置、Alembic 和测试单元，根目录只负责编排与统一验证。

**技术栈：** Git subtree、Python 3.12、FastAPI、Celery 5.4、MySQL 8、Redis 7、Vue 3、Vite 6、Vitest 2、Docker Compose v2、Nginx。

> 前端阶段说明：M0 的唯一目标是无行为变化地保留 DocMind Vue 3 基线及历史；v1.0 目标前端由 `apps/web/docs/FRONTEND.md` 定义为 React + TypeScript。Vue → React 的替换属于 ROADMAP M4，必须在稳定 API/SSE、专项规格和回归测试下执行，不得夹带进本迁移计划。

## 全局约束

- 部署基线固定为单机 Docker Compose，`2 vCPU / 2 GB RAM`。
- Knowledge Service 与 Research Service 保持独立 Python 应用、依赖单元、Alembic 迁移链和数据库所有权。本阶段仅保留两个来源仓库已有的 Knowledge 与 Research 迁移链；架构要求的 `platform_db` 独立迁移链必须由统一身份与权限专项在生产部署验收前建立。
- Research Service 禁止直接读取 `knowledge_db`、Knowledge Chroma 数据或上传文件卷。
- 跨服务复用只允许 HTTP/事件契约、`packages/contracts/` 中的纯契约类型，或有独立版本边界的无业务状态工具包。
- DocMind 来源固定为提交 `a390a2a`；ResearchMind 来源固定为提交 `40f7faa`。执行前若负责人选择更新来源提交，必须先更新本计划并重新完成基线测试。
- 导入历史不得使用 `--squash`，不得修改或 force-push 来源仓库。
- 第一阶段迁移不得改变外部业务行为、API 路径、状态机、权限语义、数据库 Schema 或 SSE 事件语义。
- 本计划的 Compose 产物是代码布局阶段的可验证编排骨架；在 `platform_db` 迁移链、统一身份、Internal Retrieval、统一研究前端及生产数据迁移分别验收前，不得将其声称为 v1.0 可发布部署。
- Chat SSE 与 Research SSE 保持独立业务解析器。
- 两个服务不得使用默认 `celery` 队列；队列分别使用 `knowledge.*` 与 `research.*`。
- 所有新增行为严格执行 SDD/TDD；纯移动步骤以移动前后同一测试集结果一致作为验收。
- 现有工作区中的用户改动必须保留；开始每个任务前执行 `git status --short`，发现非计划改动时停止并确认所有权。

---

## 文件结构

迁移完成后的第一阶段结构：

```text
evidsight/
├── apps/
│   └── web/                         # DocMind 前端基线；Research 页面在后续前端专项迁移
├── services/
│   ├── knowledge/                   # DocMind backend/ 原样迁入
│   │   ├── app/
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   ├── pytest.ini
│   │   └── alembic.ini
│   └── research/                    # ResearchMind 后端与其服务内脚本/测试
│       ├── app/
│       ├── alembic/
│       ├── tests/
│       ├── scripts/
│       ├── requirements.txt
│       ├── pytest.ini
│       └── alembic.ini
├── packages/
│   ├── contracts/                   # 此计划只建立边界与说明，不提前设计字段
│   └── frontend-shared/             # 空边界说明，不提前抽公共实现
├── deploy/
│   ├── nginx/default.conf
│   ├── prometheus/prometheus.yml
│   └── grafana/                     # 可选 profile，2C2G 默认不启动
├── scripts/
│   ├── verify_source_baselines.sh
│   ├── test_all.sh
│   └── smoke_compose.sh
├── requirements-dev.txt              # 仅根架构测试和仓库工具依赖
├── docs/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

`services/knowledge/` 和 `services/research/` 各自拥有 Dockerfile、依赖和测试配置。根目录不得生成合并后的 Python `requirements.txt`，避免依赖版本被静默统一。

---

### 任务 1：冻结并验证源仓库基线

**文件：**
- 新建：`scripts/verify_source_baselines.sh`
- 新建：`docs/migration/BASELINE_RESULTS.md`
- 修改：`.gitignore`

**输入与产物：**
- 输入：位于固定提交的同级仓库 `../docmind` 和 `../ResearchMind`。
- 产物：可执行的 `scripts/verify_source_baselines.sh`；不可变更的源版本与测试命令记录。

- [ ] **步骤 1：保护仅存在于本地的文件**

在不删除用户现有规则的前提下，将以下条目加入 `.gitignore`：

```gitignore
.superpowers/
.venv/
.env
**/.env
**/.pytest_cache/
**/__pycache__/
**/node_modules/
**/dist/
*.pyc
.coverage
htmlcov/
```

- [ ] **步骤 2：编写基线验证脚本**

创建 `scripts/verify_source_baselines.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

DOCMIND_DIR="${DOCMIND_DIR:-../docmind}"
RESEARCHMIND_DIR="${RESEARCHMIND_DIR:-../ResearchMind}"
DOCMIND_COMMIT="a390a2a"
RESEARCHMIND_COMMIT="40f7faa"

test "$(git -C "$DOCMIND_DIR" rev-parse --short=7 HEAD)" = "$DOCMIND_COMMIT"
test "$(git -C "$RESEARCHMIND_DIR" rev-parse --short=7 HEAD)" = "$RESEARCHMIND_COMMIT"
git -C "$DOCMIND_DIR" status --short
git -C "$RESEARCHMIND_DIR" status --short
```

脚本应输出源工作树变更，不得删除或隐藏它们。与待导入路径重叠的变更必须在迁移前处理。

- [ ] **步骤 3：运行基线门禁**

运行：

```bash
bash scripts/verify_source_baselines.sh
```

预期结果：退出码为 `0`，两个短版本号均匹配。对源仓库未提交的输出进行人工审查，不得自动清理。

- [ ] **步骤 4：在各自环境中运行源后端测试**

运行：

```bash
cd ../docmind/backend
.venv/bin/python -m pytest -m "not integration and not performance" --tb=short
cd ../../ResearchMind
.venv/bin/python -m pytest -m "not integration and not slow" --tb=short
```

预期结果：两条命令均通过。如果源仓库没有可用的 `.venv`，应在仓库外创建临时环境并安装其固定的 `requirements.txt`；不得向任一源仓库添加生成的环境文件。

- [ ] **步骤 5：运行源前端测试与构建**

运行：

```bash
npm --prefix ../docmind/frontend test
npm --prefix ../docmind/frontend run build
npm --prefix ../ResearchMind/frontend test
npm --prefix ../ResearchMind/frontend run build
```

预期结果：四条命令的退出码均为 `0`。

- [ ] **步骤 6：记录验证证据**

使用以下精确结构创建 `docs/migration/BASELINE_RESULTS.md`，仅将命令结果字段替换为实际观察值：

```markdown
# 源仓库基线结果

| 来源 | 提交 | 命令 | 结果 |
|:---|:---|:---|:---|
| DocMind 后端 | `a390a2a` | `.venv/bin/python -m pytest -m "not integration and not performance" --tb=short` | PASS，附实际测试数量 |
| DocMind 前端 | `a390a2a` | `npm test && npm run build` | PASS，附实际测试数量 |
| ResearchMind 后端 | `40f7faa` | `.venv/bin/python -m pytest -m "not integration and not slow" --tb=short` | PASS，附实际测试数量 |
| ResearchMind 前端 | `40f7faa` | `npm test && npm run build` | PASS，附实际测试数量 |

记录时间：ISO 8601 UTC 时间戳
```

除非已在本任务中实际运行命令，否则不得记录 `PASS`。已存在的失败必须记录具体失败测试，并在导入前获得批准。

- [ ] **步骤 7：提交基线门禁**

```bash
git add .gitignore scripts/verify_source_baselines.sh docs/migration/BASELINE_RESULTS.md
git commit -m "chore: record source migration baselines"
```

---

### 任务 2：建立 Monorepo 控制层

**文件：**
- 新建：`Makefile`
- 新建：`scripts/test_all.sh`
- 新建：`requirements-dev.txt`
- 新建：`packages/contracts/README.md`
- 新建：`packages/frontend-shared/README.md`
- 修改：`README.md`

**输入与产物：**
- 输入：各导入项目定义的独立服务测试命令。
- 产物：`make test`、`make test-knowledge`、`make test-research`、`make test-web`；明确的包边界。

- [ ] **步骤 1：编写预期失败的命令入口测试**

在创建 Makefile 前运行：

```bash
make -n test
```

预期结果：测试失败，并显示 `No rule to make target 'test'` 或等价信息。

- [ ] **步骤 2：创建根目录测试运行器**

创建 `scripts/test_all.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
```

服务内部的 `.venv` 路径是有意设计：每个 Python 服务仍是独立的依赖单元。

- [ ] **步骤 3：创建 Makefile**

```makefile
.PHONY: test test-knowledge test-research test-web build-web config compose-config

test:
	bash scripts/test_all.sh

test-knowledge:
	services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests

test-research:
	services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests

test-web:
	npm --prefix apps/web test

build-web:
	npm --prefix apps/web run build

compose-config:
	docker compose config --quiet
```

为仅在根目录运行的仓库测试创建 `requirements-dev.txt`：

```text
pytest==8.*
PyYAML==6.*
```

- [ ] **步骤 4：定义包边界，不提前实现**

创建 `packages/contracts/README.md`，内容如下：

```markdown
# EvidSight 契约

本包负责带版本的跨服务请求、响应、事件和 Evidence 契约。其中只能包含纯数据 Schema 与契约 Fixture，不得导入任一服务的 `app` 包或 ORM Model。
```

创建 `packages/frontend-shared/README.md`，内容如下：

```markdown
# EvidSight 前端共享边界

本目录仅为经过多模块共用验证的稳定、框架级前端能力保留。迁移不得将服务特定的 SSE 事件或业务 Store 移入此处。
```

- [ ] **步骤 5：记录根目录命令与所有权**

更新 `README.md`，写明目标目录树、前置条件、服务内部环境设置、根目录验证命令，并链接 `docs/specs/ARCHITECTURE.md`、`docs/specs/PRD.md` 和本计划。不得重复架构规则。

- [ ] **步骤 6：验证命令入口**

运行：

```bash
make -n test
make -n test-knowledge
make -n test-research
make -n test-web
make -n build-web
```

预期结果：每条命令都输出准确的子命令，不出现目标缺失错误。

- [ ] **步骤 7：提交控制层**

```bash
git add Makefile README.md requirements-dev.txt scripts/test_all.sh packages/contracts/README.md packages/frontend-shared/README.md
git commit -m "chore: add monorepo command and package boundaries"
```

---

### 任务 3：将 DocMind 后端历史导入为 Knowledge Service

**文件：**
- 通过历史导入新建：`services/knowledge/**`
- 修改：`services/knowledge/.env.example`

**输入与产物：**
- 输入：DocMind 提交 `a390a2a` 的 `backend/` 子树。
- 产物：`services/knowledge/app`、测试、Alembic 历史、依赖与服务内部配置。

- [ ] **步骤 1：拉取固定的源历史**

```bash
git remote add migration-docmind ../docmind
git fetch migration-docmind
git cat-file -e a390a2a^{commit}
git branch imports/docmind-a390a2a a390a2a
```

预期结果：`git rev-parse --short=7 imports/docmind-a390a2a` 输出 `a390a2a`。

- [ ] **步骤 2：拆分后端历史**

```bash
git subtree split --prefix=backend imports/docmind-a390a2a -b imports/docmind-backend
```

预期结果：该分支根目录包含 `app/`、`tests/`、`alembic/`、`requirements.txt`、`pytest.ini` 和 `alembic.ini`。

- [ ] **步骤 3：不压缩历史地导入**

```bash
git subtree add --prefix=services/knowledge imports/docmind-backend
```

预期结果：`git log --follow -- services/knowledge/app/main.py` 包含早于 `a390a2a` 的提交。

- [ ] **步骤 4：如历史中含有本地运行产物，则将其移除**

首先检查已跟踪文件：

```bash
git ls-files services/knowledge | rg '(^|/)(\.env|\.venv|\.pytest_cache|__pycache__|uploads|chroma_data)(/|$)'
```

对报告的每个已跟踪生成路径，仅使用 `git rm -r <报告的路径>` 移除该精确目标。保留 `.env.example`、测试 Fixture 和有意纳入版本控制的示例文档。

- [ ] **步骤 5：添加服务标识配置**

在 `services/knowledge/.env.example` 中保留所有现有变量，仅添加或重命名部署标识变量：

```dotenv
SERVICE_NAME=evidsight-knowledge
MYSQL_DATABASE=knowledge_db
REDIS_KEY_PREFIX=evidsight:knowledge
CELERY_INGEST_QUEUE=knowledge.ingest
CELERY_DELETE_QUEUE=knowledge.delete
```

此步骤仅修改默认值，不得改变 API 行为。

- [ ] **步骤 6：重建服务环境并运行测试**

```bash
python3.12 -m venv services/knowledge/.venv
services/knowledge/.venv/bin/pip install -r services/knowledge/requirements.txt
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests -m "not integration and not performance" --tb=short
```

预期结果：选定测试的数量和结果与 `docs/migration/BASELINE_RESULTS.md` 一致。

- [ ] **步骤 7：验证 Alembic 仍保持独立**

```bash
cd services/knowledge
.venv/bin/alembic heads
.venv/bin/alembic history
```

预期结果：原 DocMind head 和全部 16 个迁移文件均存在，不出现 ResearchMind revision。

- [ ] **步骤 8：提交导入后规范化变更**

```bash
git add services/knowledge
git commit -m "chore(knowledge): normalize imported service configuration"
```

---

### 任务 4：将 DocMind 前端历史导入为统一 Web 基线

**文件：**
- 通过历史导入新建：`apps/web/**`
- 修改：`apps/web/package.json`

**输入与产物：**
- 输入：DocMind 提交 `a390a2a` 的 `frontend/` 子树。
- 产物：M0 阶段唯一的 `apps/web` Vue 迁移基线及其现有测试；它不是 M4 的最终 React 交付物。

- [ ] **步骤 1：拆分并导入前端历史**

```bash
git subtree split --prefix=frontend imports/docmind-a390a2a -b imports/docmind-frontend
git subtree add --prefix=apps/web imports/docmind-frontend
```

预期结果：`apps/web/src`、`apps/web/tests`、`apps/web/package.json` 和 `apps/web/package-lock.json` 均存在，且 `git log --follow -- apps/web/src/main.js` 能追溯到 DocMind 历史。

- [ ] **步骤 2：将生成的前端产物移出版本跟踪**

```bash
git ls-files apps/web | rg '(^|/)(node_modules|dist|\.vite|\.pytest_cache)(/|$)'
```

仅对报告的生成路径使用精确的 `git rm -r` 目标进行移除。

- [ ] **步骤 3：重命名包标识，不改变依赖**

仅修改 `apps/web/package.json` 中的以下值：

```json
{
  "name": "evidsight-web",
  "version": "1.0.0",
  "private": true
}
```

在本迁移任务中保留脚本和依赖版本。

- [ ] **步骤 4：按锁定文件安装并验证一致性**

```bash
npm --prefix apps/web ci
npm --prefix apps/web test
npm --prefix apps/web run build
```

预期结果：测试数量和结果与 DocMind 前端基线一致，生产构建的退出码为 `0`。

- [ ] **步骤 5：提交前端规范化变更**

```bash
git add apps/web
git commit -m "chore(web): establish unified frontend baseline"
```

---

### 任务 5：导入并整形 ResearchMind 历史

**文件：**
- 临时导入：`.migration/researchmind/**`
- 通过移动新建：`services/research/**`
- 新建：`docs/migration/RESEARCH_FRONTEND_SOURCE.md`
- 完成移动记录后删除：`.migration/researchmind/`

**输入与产物：**
- 输入：位于提交 `40f7faa` 的完整 ResearchMind 仓库。
- 产物：位于归属目标路径下的 Research 后端、测试、迁移、服务脚本和可观测性资产；用于后续前端迁移的可追溯记录。

- [ ] **步骤 1：拉取并导入完整的固定历史**

```bash
git remote add migration-researchmind ../ResearchMind
git fetch migration-researchmind
git cat-file -e 40f7faa^{commit}
git branch imports/researchmind-40f7faa 40f7faa
git subtree add --prefix=.migration/researchmind imports/researchmind-40f7faa
```

不得使用 `--squash`。

- [ ] **步骤 2：创建 Research Service 目标路径**

```bash
mkdir -p services/research
git mv .migration/researchmind/app services/research/app
git mv .migration/researchmind/alembic services/research/alembic
git mv .migration/researchmind/tests services/research/tests
git mv .migration/researchmind/scripts services/research/scripts
git mv .migration/researchmind/requirements.txt services/research/requirements.txt
git mv .migration/researchmind/pytest.ini services/research/pytest.ini
git mv .migration/researchmind/alembic.ini services/research/alembic.ini
git mv .migration/researchmind/.env.example services/research/.env.example
git mv .migration/researchmind/docker-entrypoint.sh services/research/docker-entrypoint.sh
git mv .migration/researchmind/Dockerfile.backend services/research/Dockerfile
```

- [ ] **步骤 3：移动服务所有的文档与可观测性资产**

```bash
git mv .migration/researchmind/docs services/research/docs
mkdir -p deploy/prometheus deploy/grafana
git mv .migration/researchmind/prometheus.yml deploy/prometheus/prometheus.yml
git mv .migration/researchmind/grafana/provisioning deploy/grafana/provisioning
git mv .migration/researchmind/grafana/dashboards deploy/grafana/dashboards
```

- [ ] **步骤 4：在裁剪前记录 Research 前端来源**

创建 `docs/migration/RESEARCH_FRONTEND_SOURCE.md`：

```markdown
# Research 前端迁移来源

- 源仓库：`../ResearchMind`
- 固定提交：`40f7faa`
- 已导入历史路径：`.migration/researchmind/frontend/`
- 目标集成路径：`apps/web/src/modules/research/`
- 迁移所属专项：统一前端信息架构计划

源前端有意不在 EvidSight 根目录中保持可运行状态。其页面、Store、API 客户端行为、SSE 解析器、测试和原型必须先通过前端专项设计建立映射，再进行选择性迁移。
```

- [ ] **步骤 5：审查已跟踪路径后移除非运行时导入副本**

运行：

```bash
find .migration/researchmind -maxdepth 2 -mindepth 1 -print | sort
```

目标目录树中不得保留可运行的第二个前端。仅在确认所有后端、测试、迁移、服务文档和必需部署资产已在步骤 2–3 中移动，且已创建前端来源记录后，才能使用 `git rm -r .migration/researchmind` 移除剩余目录。

- [ ] **步骤 6：仅规范化 Research Service 标识**

将现有 `.env.example` 移到 `services/research/.env.example` 并保留其全部变量，然后设置以下部署默认值：

```dotenv
SERVICE_NAME=evidsight-research
MYSQL_DATABASE=research_db
REDIS_KEY_PREFIX=evidsight:research
CELERY_EXECUTE_QUEUE=research.execute
CELERY_RECOVERY_QUEUE=research.recovery
CELERY_PERIODIC_QUEUE=research.periodic
```

不得将 Knowledge 变量或依赖合并到此文件。

- [ ] **步骤 7：重建服务环境并运行测试**

```bash
python3.12 -m venv services/research/.venv
services/research/.venv/bin/pip install -r services/research/requirements.txt
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests -m "not integration and not slow" --tb=short
```

预期结果：选定测试的数量和结果与 ResearchMind 后端基线一致。

- [ ] **步骤 8：验证导入与 Alembic 隔离**

```bash
PYTHONPATH=services/research services/research/.venv/bin/python -c "from app.main import app; print(app.title)"
cd services/research
.venv/bin/alembic heads
.venv/bin/alembic history
```

预期结果：应用导入成功；原 ResearchMind head 和全部 11 个迁移文件均存在，不出现 DocMind revision。

- [ ] **步骤 9：提交整形变更**

```bash
git add services/research deploy/prometheus deploy/grafana docs/migration/RESEARCH_FRONTEND_SOURCE.md
git commit -m "chore(research): import service with preserved history"
```

---

### 任务 6：使服务构建上下文保持独立

**文件：**
- 新建：`services/knowledge/Dockerfile`
- 修改：`services/research/Dockerfile`
- 修改：`services/research/docker-entrypoint.sh`
- 新建：`services/knowledge/.dockerignore`
- 新建：`services/research/.dockerignore`
- 新建：`tests/architecture/test_service_boundaries.py`

**输入与产物：**
- 输入：服务内部的 `requirements.txt` 和 `app` 包。
- 产物：仅从各自服务目录构建的镜像 `evidsight/knowledge:<version>` 和 `evidsight/research:<version>`。

- [ ] **步骤 1：编写预期失败的边界测试**

创建 `tests/architecture/test_service_boundaries.py`：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_each_service_owns_its_build_context():
    for service in ("knowledge", "research"):
        root = ROOT / "services" / service
        assert (root / "Dockerfile").is_file()
        assert (root / "requirements.txt").is_file()
        assert (root / ".dockerignore").is_file()


def test_services_do_not_import_each_other_app_package():
    knowledge = "\n".join(
        p.read_text(errors="ignore") for p in (ROOT / "services/knowledge/app").rglob("*.py")
    )
    research = "\n".join(
        p.read_text(errors="ignore") for p in (ROOT / "services/research/app").rglob("*.py")
    )
    assert "services.research.app" not in knowledge
    assert "services.knowledge.app" not in research
```

- [ ] **步骤 2：运行测试并确认其失败**

```bash
python3.12 -m pytest tests/architecture/test_service_boundaries.py -v
```

预期结果：测试失败，因为至少有一个 `.dockerignore` 不存在。

- [ ] **步骤 3：规范化 Dockerfile**

每个 Dockerfile 必须使用所属服务目录作为构建上下文，并包含以下等价阶段：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app
```

保留每个源镜像的操作系统包和入口行为。本任务不得从 `../../packages` 复制文件，因为契约尚无运行时实现。

- [ ] **步骤 4：添加确定性 Docker 忽略规则**

在两个服务中创建相同且范围明确的 `.dockerignore`：

```dockerignore
.env
.venv
.pytest_cache
__pycache__
*.pyc
.coverage
htmlcov
tests
```

- [ ] **步骤 5：运行边界测试与镜像构建**

```bash
python3.12 -m pytest tests/architecture/test_service_boundaries.py -v
docker build -t evidsight/knowledge:migration services/knowledge
docker build -t evidsight/research:migration services/research
```

预期结果：测试通过；两个镜像均能构建，且不读取各自服务上下文之外的文件。

- [ ] **步骤 6：对两个镜像执行导入冒烟测试**

```bash
docker run --rm --entrypoint python evidsight/knowledge:migration -c "from app.main import app; print(app.title)"
docker run --rm --entrypoint python evidsight/research:migration -c "from app.main import app; print(app.title)"
```

预期结果：两条命令的退出码均为 `0`，并输出各自的应用标题。

- [ ] **步骤 7：提交独立构建上下文**

```bash
git add services/knowledge services/research tests/architecture/test_service_boundaries.py
git commit -m "build: isolate backend service images"
```

---

### 任务 7：添加 2C2G Compose 与 Nginx 编排骨架

**文件：**
- 新建：`docker-compose.yml`
- 新建：`.env.example`
- 新建：`deploy/nginx/default.conf`
- 新建：`scripts/smoke_compose.sh`
- 新建：`tests/architecture/test_compose_contract.py`

**输入与产物：**
- 输入：前续任务产生的服务镜像与前端构建产物。
- 产物：仅对外暴露 Nginx 的单机编排骨架；服务命名和队列与 `docs/specs/ARCHITECTURE.md` 一致。该产物不构成 v1.0 生产部署验收。

- [ ] **步骤 1：编写预期失败的 Compose 契约测试**

创建 `tests/architecture/test_compose_contract.py`：

```python
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_required_services_and_external_port_boundary():
    model = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = model["services"]
    expected = {
        "nginx", "mysql", "redis", "knowledge-api", "knowledge-worker",
        "research-api", "research-worker", "research-beat",
    }
    assert expected <= services.keys()
    assert "ports" in services["nginx"]
    for name in expected - {"nginx"}:
        assert "ports" not in services[name]


def test_workers_use_explicit_queues():
    model = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    knowledge = " ".join(model["services"]["knowledge-worker"]["command"])
    research = " ".join(model["services"]["research-worker"]["command"])
    assert "knowledge.ingest,knowledge.delete" in knowledge
    assert "research.execute,research.recovery,research.periodic" in research
```

使用 `python3.12 -m pip install -r requirements-dev.txt` 安装已定义的根目录架构测试依赖；除非服务本身导入 PyYAML，否则不得将其添加到任一服务依赖中。

- [ ] **步骤 2：运行契约测试并确认其失败**

```bash
python3.12 -m pytest tests/architecture/test_compose_contract.py -v
```

预期结果：测试失败，因为 `docker-compose.yml` 不存在。

- [ ] **步骤 3：按精确的服务与隔离规则创建 Compose**

定义测试中的八个服务。必需设置如下：

```yaml
services:
  nginx:
    ports: ["80:80"]
  knowledge-api:
    build: {context: ./services/knowledge, dockerfile: Dockerfile}
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
    mem_limit: 256m
  knowledge-worker:
    build: {context: ./services/knowledge, dockerfile: Dockerfile}
    command: ["celery", "-A", "app.ingest.celery_app", "worker", "--loglevel=info", "--concurrency=1", "-Q", "knowledge.ingest,knowledge.delete"]
    mem_limit: 320m
  research-api:
    build: {context: ./services/research, dockerfile: Dockerfile}
    mem_limit: 256m
  research-worker:
    build: {context: ./services/research, dockerfile: Dockerfile}
    command: ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=1", "-Q", "research.execute,research.recovery,research.periodic"]
    mem_limit: 320m
  research-beat:
    build: {context: ./services/research, dockerfile: Dockerfile}
    mem_limit: 64m
  mysql:
    image: mysql:8.0
    mem_limit: 448m
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "96mb", "--maxmemory-policy", "noeviction"]
    mem_limit: 96m
```

补全健康检查、`docs/specs/ARCHITECTURE.md` 中的五个命名卷、edge/internal 网络、服务内部环境文件、MySQL UTC/utf8mb4 设置和依赖健康条件。不得暴露后端或数据端口。

- [ ] **步骤 4：创建 Nginx 路由**

`deploy/nginx/default.conf` 必须托管 `apps/web/dist`，将公开的 Knowledge 和 Research 路由代理到各自 API，对 SSE 禁用代理缓冲，并拒绝内部路由：

```nginx
location ^~ /internal/v1/ {
    return 404;
}

location /api/research/ {
    proxy_pass http://research-api:8000;
    proxy_buffering off;
    proxy_read_timeout 3600s;
}

location /api/ {
    proxy_pass http://knowledge-api:8000;
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

- [ ] **步骤 5：添加环境变量 Schema 与配置冒烟脚本**

`.env.example` 仅列出 MySQL 凭据、JWT 设置、服务数据库 URL、隔离的 Redis URL/DB、Provider 密钥、镜像版本和备份路径的变量名，不得包含可用密钥。

创建 `scripts/smoke_compose.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
docker compose config --quiet
docker compose up -d --build
curl --fail --retry 20 --retry-delay 3 http://localhost/api/health
curl --fail --retry 20 --retry-delay 3 http://localhost/api/research/health
test "$(curl -sS -o /dev/null -w '%{http_code}' http://localhost/internal/v1/retrieval/search)" = "404"
docker compose ps
```

- [ ] **步骤 6：运行静态与运行时验证**

```bash
python3.12 -m pytest tests/architecture/test_compose_contract.py -v
docker compose --env-file .env.test config --quiet
bash scripts/smoke_compose.sh
```

预期结果：契约测试通过；Compose 配置有效；两个公开健康检查均返回 2xx；从外部访问 Internal API 返回 `404`；所有必需容器处于健康状态。

- [ ] **步骤 7：停止服务但不删除持久化数据**

```bash
docker compose down
```

常规验证期间不得使用 `down -v`。

- [ ] **步骤 8：提交编排骨架**

```bash
git add docker-compose.yml .env.example deploy/nginx/default.conf scripts/smoke_compose.sh tests/architecture/test_compose_contract.py
git commit -m "build: add single-node EvidSight deployment"
```

---

### 任务 8：添加跨仓库验证与第一阶段迁移验收

**文件：**
- 修改：`scripts/test_all.sh`
- 新建：`tests/architecture/test_repository_layout.py`
- 新建：`docs/migration/MIGRATION_ACCEPTANCE.md`
- 修改：`docs/CHANGELOG.md`

**输入与产物：**
- 输入：所有已导入的服务测试、Web 测试、架构测试和镜像构建。
- 产物：一条可重复执行的第一阶段迁移验收命令，以及记录的一致性证据。

- [ ] **步骤 1：编写仓库布局测试**

创建 `tests/architecture/test_repository_layout.py`：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_target_layout_exists():
    required = [
        "apps/web/package.json",
        "services/knowledge/app/main.py",
        "services/knowledge/alembic.ini",
        "services/research/app/main.py",
        "services/research/alembic.ini",
        "packages/contracts/README.md",
        "docker-compose.yml",
        "deploy/nginx/default.conf",
    ]
    assert all((ROOT / path).is_file() for path in required)


def test_no_second_runnable_frontend_exists():
    package_files = sorted(ROOT.glob("**/package.json"))
    tracked = [p for p in package_files if "node_modules" not in p.parts]
    assert tracked == [ROOT / "apps/web/package.json"]


def test_migration_scratch_tree_is_gone():
    assert not (ROOT / ".migration").exists()
```

- [ ] **步骤 2：运行布局测试**

```bash
python3.12 -m pytest tests/architecture/test_repository_layout.py tests/architecture/test_service_boundaries.py tests/architecture/test_compose_contract.py -v
```

预期结果：测试通过。

- [ ] **步骤 3：扩展全量测试运行器**

在 `scripts/test_all.sh` 开头加入架构测试，并在末尾加入 Web 构建：

```bash
python3.12 -m pytest tests/architecture -v
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
npm --prefix apps/web run build
docker compose config --quiet
```

- [ ] **步骤 4：运行完整迁移验证**

```bash
bash scripts/verify_source_baselines.sh
bash scripts/test_all.sh
docker build -t evidsight/knowledge:migration services/knowledge
docker build -t evidsight/research:migration services/research
```

预期结果：架构测试、两个后端测试集、Web 测试、Web 构建、Compose 解析和两个镜像构建均通过。

- [ ] **步骤 5：验证历史保留**

```bash
git log --follow --oneline -- services/knowledge/app/main.py | tail -5
git log --follow --oneline -- apps/web/src/main.js | tail -5
git log --follow --oneline -- services/research/app/main.py | tail -5
```

预期结果：每条命令均显示早于 EvidSight 导入提交的源项目提交。

- [ ] **步骤 6：编写迁移验收证据**

创建 `docs/migration/MIGRATION_ACCEPTANCE.md`，包含：

- 固定的源提交；
- 步骤 2、4 和 5 中的精确命令；
- 实际观察到的测试数量和结果；
- 已导入的 Alembic head 和迁移数量（固定基线中 Knowledge 为 `16`、Research 为 `11`）；
- Docker 镜像 ID；
- 已知源失败或已批准偏差；
- 确认没有有意改变业务 API、状态、权限或 SSE 行为；
- 回滚点：首次 subtree 导入之前的紧邻提交；
- 明确声明本验收仅覆盖代码布局迁移第一阶段，不覆盖 `platform_db` 迁移链、统一身份、Internal Retrieval、统一研究前端、生产数据迁移或 v1.0 发布验收。

- [ ] **步骤 7：更新变更日志**

向 `docs/CHANGELOG.md` 添加迁移条目，链接到 `MIGRATION_ACCEPTANCE.md`，且仅陈述结构性成果。不得声称本计划已实现统一身份、Internal Retrieval 或研究前端集成。

- [ ] **步骤 8：提交验收证据**

```bash
git add scripts/test_all.sh tests/architecture docs/migration/MIGRATION_ACCEPTANCE.md docs/CHANGELOG.md
git commit -m "test: verify monorepo migration parity"
```

---

## 迁移回滚

在任务 3 之前，记录干净的控制层提交：

```bash
git rev-parse HEAD
```

如果导入任务失败，应保留诊断信息，在导入分支上前向修复，或放弃该未合并分支。不得在包含用户变更的工作树中运行 `git reset --hard`。由于每个 subtree 导入和规范化变更都单独提交，审查者可以拒绝某个导入单元，而不必丢弃已接受的单元。

仅当任务 8 的证据通过时，才能声称“Monorepo 代码布局迁移第一阶段完成”。在生产数据迁移、统一前端、身份集成、部署演练和回滚演练分别通过验收前，源仓库仍保持可写，并作为未完成迁移部分的实现基线；本代码布局计划不授权归档源仓库，也不代表 EvidSight v1.0 已可发布。
