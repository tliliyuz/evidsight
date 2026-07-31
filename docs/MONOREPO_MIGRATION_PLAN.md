# EvidSight Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 DocMind 与 ResearchMind 按已确认的双服务边界迁入 EvidSight Monorepo，在不改变业务行为的前提下形成可独立测试、统一构建和单机部署的仓库基线。

**Architecture:** 使用非压缩 Git subtree 保留来源历史：DocMind 的 `backend/` 与 `frontend/` 分别导入 `services/knowledge/` 和 `apps/web/`；ResearchMind 固定提交整体导入临时前缀后，以可审查的 `git mv` 整形到 `services/research/`，研究前端保留为后续统一前端迁移输入。两个 Python 服务继续作为独立依赖、配置、Alembic 和测试单元，根目录只负责编排、统一验证与部署。

**Tech Stack:** Git subtree、Python 3.12、FastAPI、Celery 5.4、MySQL 8、Redis 7、Vue 3、Vite 6、Vitest 2、Docker Compose v2、Nginx。

## Global Constraints

- 部署基线固定为单机 Docker Compose，`2 vCPU / 2 GB RAM`。
- Knowledge Service 与 Research Service 保持独立 Python 应用、依赖单元、Alembic 迁移链和数据库所有权。
- Research Service 禁止直接读取 `knowledge_db`、Knowledge Chroma 数据或上传文件卷。
- 跨服务复用只允许 HTTP/事件契约、`packages/contracts/` 中的纯契约类型，或有独立版本边界的无业务状态工具包。
- DocMind 来源固定为提交 `a390a2a`；ResearchMind 来源固定为提交 `40f7faa`。执行前若负责人选择更新来源提交，必须先更新本计划并重新完成基线测试。
- 导入历史不得使用 `--squash`，不得修改或 force-push 来源仓库。
- 第一阶段迁移不得改变外部业务行为、API 路径、状态机、权限语义、数据库 Schema 或 SSE 事件语义。
- Chat SSE 与 Research SSE 保持独立业务解析器。
- 两个服务不得使用默认 `celery` 队列；队列分别使用 `knowledge.*` 与 `research.*`。
- 所有新增行为严格执行 SDD/TDD；纯移动步骤以移动前后同一测试集结果一致作为验收。
- 现有工作区中的用户改动必须保留；开始每个任务前执行 `git status --short`，发现非计划改动时停止并确认所有权。

---

## File Structure

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

### Task 1: Freeze and Verify Source Baselines

**Files:**
- Create: `scripts/verify_source_baselines.sh`
- Create: `docs/migration/BASELINE_RESULTS.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: sibling repositories `../docmind` and `../ResearchMind` at the pinned commits.
- Produces: executable `scripts/verify_source_baselines.sh`; an immutable record of source revisions and test commands.

- [ ] **Step 1: Protect local-only files**

Add these entries to `.gitignore` without removing existing user rules:

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

- [ ] **Step 2: Write the baseline verification script**

Create `scripts/verify_source_baselines.sh`:

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

The script prints source worktree changes rather than deleting or hiding them. Any change overlapping imported paths must be resolved before migration.

- [ ] **Step 3: Run the baseline guard**

Run:

```bash
bash scripts/verify_source_baselines.sh
```

Expected: exit code `0`; both short revisions match. Dirty source output is reviewed, not automatically cleaned.

- [ ] **Step 4: Run source backend tests from their own environments**

Run:

```bash
cd ../docmind/backend
.venv/bin/python -m pytest -m "not integration and not performance" --tb=short
cd ../../ResearchMind
.venv/bin/python -m pytest -m "not integration and not slow" --tb=short
```

Expected: both commands pass. If a source repository has no usable `.venv`, create a temporary environment outside the repository and install its pinned `requirements.txt`; do not add generated environment files to either source repository.

- [ ] **Step 5: Run source frontend tests and builds**

Run:

```bash
npm --prefix ../docmind/frontend test
npm --prefix ../docmind/frontend run build
npm --prefix ../ResearchMind/frontend test
npm --prefix ../ResearchMind/frontend run build
```

Expected: all four commands exit `0`.

- [ ] **Step 6: Record the evidence**

Create `docs/migration/BASELINE_RESULTS.md` with this exact structure and replace only command outcome fields with observed values:

```markdown
# Source Baseline Results

| Source | Commit | Command | Result |
|:---|:---|:---|:---|
| DocMind backend | `a390a2a` | `.venv/bin/python -m pytest -m "not integration and not performance" --tb=short` | PASS with observed test count |
| DocMind frontend | `a390a2a` | `npm test && npm run build` | PASS with observed test count |
| ResearchMind backend | `40f7faa` | `.venv/bin/python -m pytest -m "not integration and not slow" --tb=short` | PASS with observed test count |
| ResearchMind frontend | `40f7faa` | `npm test && npm run build` | PASS with observed test count |

Recorded at: ISO 8601 UTC timestamp
```

Do not record `PASS` unless the command was run in this task. A pre-existing failure must be documented with its failing test and approved before import.

- [ ] **Step 7: Commit the baseline gate**

```bash
git add .gitignore scripts/verify_source_baselines.sh docs/migration/BASELINE_RESULTS.md
git commit -m "chore: record source migration baselines"
```

---

### Task 2: Create the Monorepo Control Plane

**Files:**
- Create: `Makefile`
- Create: `scripts/test_all.sh`
- Create: `requirements-dev.txt`
- Create: `packages/contracts/README.md`
- Create: `packages/frontend-shared/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: independent service test commands defined by each imported project.
- Produces: `make test`, `make test-knowledge`, `make test-research`, `make test-web`; explicit package boundaries.

- [ ] **Step 1: Write a failing command-surface test**

Run before creating the Makefile:

```bash
make -n test
```

Expected: FAIL with `No rule to make target 'test'` or equivalent.

- [ ] **Step 2: Create the root test runner**

Create `scripts/test_all.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
```

The service-local `.venv` paths are deliberate: each Python service remains an independent dependency unit.

- [ ] **Step 3: Create the Makefile**

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

Create `requirements-dev.txt` for root-only repository tests:

```text
pytest==8.*
PyYAML==6.*
```

- [ ] **Step 4: Define package boundaries without premature implementation**

Create `packages/contracts/README.md` stating:

```markdown
# EvidSight Contracts

This package owns versioned cross-service request, response, event, and Evidence contracts. It contains pure data schemas and contract fixtures only. It must not import either service's `app` package or ORM models.
```

Create `packages/frontend-shared/README.md` stating:

```markdown
# EvidSight Frontend Shared

This directory is reserved for stable, framework-level frontend capabilities proven to be shared by multiple modules. Migration must not move service-specific SSE events or business stores here.
```

- [ ] **Step 5: Document root commands and ownership**

Update `README.md` with the target tree, prerequisites, service-local environment setup, root verification commands, and links to `docs/ARCHITECTURE.md`, `docs/PRD.md`, and this plan. Do not duplicate architecture rules.

- [ ] **Step 6: Verify the command surface**

Run:

```bash
make -n test
make -n test-knowledge
make -n test-research
make -n test-web
make -n build-web
```

Expected: each command prints the exact child command without a missing-target error.

- [ ] **Step 7: Commit the control plane**

```bash
git add Makefile README.md requirements-dev.txt scripts/test_all.sh packages/contracts/README.md packages/frontend-shared/README.md
git commit -m "chore: add monorepo command and package boundaries"
```

---

### Task 3: Import DocMind Backend History as Knowledge Service

**Files:**
- Create through history import: `services/knowledge/**`
- Modify: `services/knowledge/.env.example`

**Interfaces:**
- Consumes: DocMind commit `a390a2a`, subtree `backend/`.
- Produces: `services/knowledge/app`, tests, Alembic history, requirements, and service-local configuration.

- [ ] **Step 1: Fetch the pinned source history**

```bash
git remote add migration-docmind ../docmind
git fetch migration-docmind
git cat-file -e a390a2a^{commit}
git branch imports/docmind-a390a2a a390a2a
```

Expected: `git rev-parse --short=7 imports/docmind-a390a2a` prints `a390a2a`.

- [ ] **Step 2: Split the backend history**

```bash
git subtree split --prefix=backend imports/docmind-a390a2a -b imports/docmind-backend
```

Expected: the branch contains `app/`, `tests/`, `alembic/`, `requirements.txt`, `pytest.ini`, and `alembic.ini` at its root.

- [ ] **Step 3: Import without squashing**

```bash
git subtree add --prefix=services/knowledge imports/docmind-backend
```

Expected: `git log --follow -- services/knowledge/app/main.py` includes commits preceding `a390a2a`.

- [ ] **Step 4: Remove local runtime artifacts if history contains them**

Use tracked-file checks first:

```bash
git ls-files services/knowledge | rg '(^|/)(\.env|\.venv|\.pytest_cache|__pycache__|uploads|chroma_data)(/|$)'
```

For each tracked generated path reported, remove only that exact path with `git rm -r <reported-path>`. Keep `.env.example`, test fixtures, and intentionally versioned sample documents.

- [ ] **Step 5: Add service identity configuration**

In `services/knowledge/.env.example`, preserve every existing variable and add or rename only the deployment identity variables:

```dotenv
SERVICE_NAME=evidsight-knowledge
MYSQL_DATABASE=knowledge_db
REDIS_KEY_PREFIX=evidsight:knowledge
CELERY_INGEST_QUEUE=knowledge.ingest
CELERY_DELETE_QUEUE=knowledge.delete
```

This step changes defaults only; it must not change API behavior.

- [ ] **Step 6: Recreate the service environment and run tests**

```bash
python3.12 -m venv services/knowledge/.venv
services/knowledge/.venv/bin/pip install -r services/knowledge/requirements.txt
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests -m "not integration and not performance" --tb=short
```

Expected: same selected test count and outcome as `docs/migration/BASELINE_RESULTS.md`.

- [ ] **Step 7: Verify Alembic remains independent**

```bash
cd services/knowledge
.venv/bin/alembic heads
.venv/bin/alembic history
```

Expected: the original DocMind head and all 16 migration files are present; no ResearchMind revision appears.

- [ ] **Step 8: Commit post-import normalization**

```bash
git add services/knowledge
git commit -m "chore(knowledge): normalize imported service configuration"
```

---

### Task 4: Import DocMind Frontend History as the Unified Web Baseline

**Files:**
- Create through history import: `apps/web/**`
- Modify: `apps/web/package.json`

**Interfaces:**
- Consumes: DocMind commit `a390a2a`, subtree `frontend/`.
- Produces: the sole `apps/web` Vue application and its existing tests.

- [ ] **Step 1: Split and import frontend history**

```bash
git subtree split --prefix=frontend imports/docmind-a390a2a -b imports/docmind-frontend
git subtree add --prefix=apps/web imports/docmind-frontend
```

Expected: `apps/web/src`, `apps/web/tests`, `apps/web/package.json`, and `apps/web/package-lock.json` exist, and `git log --follow -- apps/web/src/main.js` reaches DocMind history.

- [ ] **Step 2: Remove generated frontend artifacts from tracking**

```bash
git ls-files apps/web | rg '(^|/)(node_modules|dist|\.vite|\.pytest_cache)(/|$)'
```

Remove only reported generated paths using exact `git rm -r` targets.

- [ ] **Step 3: Rename package identity without changing dependencies**

Change only these values in `apps/web/package.json`:

```json
{
  "name": "evidsight-web",
  "version": "1.0.0",
  "private": true
}
```

Preserve scripts and dependency versions in this migration task.

- [ ] **Step 4: Install from the lockfile and verify parity**

```bash
npm --prefix apps/web ci
npm --prefix apps/web test
npm --prefix apps/web run build
```

Expected: test count and outcome match the DocMind frontend baseline; production build exits `0`.

- [ ] **Step 5: Commit frontend normalization**

```bash
git add apps/web
git commit -m "chore(web): establish unified frontend baseline"
```

---

### Task 5: Import and Reshape ResearchMind History

**Files:**
- Import temporarily: `.migration/researchmind/**`
- Create through moves: `services/research/**`
- Create: `docs/migration/RESEARCH_FRONTEND_SOURCE.md`
- Delete after recorded moves: `.migration/researchmind/`

**Interfaces:**
- Consumes: full ResearchMind repository at commit `40f7faa`.
- Produces: Research backend, tests, migrations, service scripts and observability assets under owned target paths; a traceable record for later frontend migration.

- [ ] **Step 1: Fetch and import the full pinned history**

```bash
git remote add migration-researchmind ../ResearchMind
git fetch migration-researchmind
git cat-file -e 40f7faa^{commit}
git branch imports/researchmind-40f7faa 40f7faa
git subtree add --prefix=.migration/researchmind imports/researchmind-40f7faa
```

Do not use `--squash`.

- [ ] **Step 2: Create the Research service destination**

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

- [ ] **Step 3: Move service-owned documentation and observability assets**

```bash
git mv .migration/researchmind/docs services/research/docs
mkdir -p deploy/prometheus deploy/grafana
git mv .migration/researchmind/prometheus.yml deploy/prometheus/prometheus.yml
git mv .migration/researchmind/grafana/provisioning deploy/grafana/provisioning
git mv .migration/researchmind/grafana/dashboards deploy/grafana/dashboards
```

- [ ] **Step 4: Record the Research frontend source before pruning**

Create `docs/migration/RESEARCH_FRONTEND_SOURCE.md`:

```markdown
# Research Frontend Migration Source

- Source repository: `../ResearchMind`
- Pinned commit: `40f7faa`
- Imported historical path: `.migration/researchmind/frontend/`
- Target integration path: `apps/web/src/modules/research/`
- Migration owner: unified frontend information architecture plan

The source frontend is intentionally not made runnable in the EvidSight root. Its pages, stores, API client behavior, SSE parser, tests, and prototypes must be mapped through the frontend专项 design before selective migration.
```

- [ ] **Step 5: Remove non-runtime imported copies after reviewing tracked paths**

Run:

```bash
find .migration/researchmind -maxdepth 2 -mindepth 1 -print | sort
```

Keep no runnable second frontend in the target tree. Remove the remaining `.migration/researchmind` directory with `git rm -r .migration/researchmind` only after confirming all backend, test, migration, service docs and required deployment assets were moved in Steps 2–3 and the frontend source record was created.

- [ ] **Step 6: Normalize Research service identity only**

Preserve every existing `.env.example` variable by moving it to `services/research/.env.example`, then set these deployment defaults:

```dotenv
SERVICE_NAME=evidsight-research
MYSQL_DATABASE=research_db
REDIS_KEY_PREFIX=evidsight:research
CELERY_EXECUTE_QUEUE=research.execute
CELERY_RECOVERY_QUEUE=research.recovery
CELERY_PERIODIC_QUEUE=research.periodic
```

Do not merge Knowledge variables or dependencies into this file.

- [ ] **Step 7: Recreate the service environment and run tests**

```bash
python3.12 -m venv services/research/.venv
services/research/.venv/bin/pip install -r services/research/requirements.txt
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests -m "not integration and not slow" --tb=short
```

Expected: same selected test count and outcome as the ResearchMind backend baseline.

- [ ] **Step 8: Verify imports and Alembic isolation**

```bash
PYTHONPATH=services/research services/research/.venv/bin/python -c "from app.main import app; print(app.title)"
cd services/research
.venv/bin/alembic heads
.venv/bin/alembic history
```

Expected: application import succeeds; the original ResearchMind head and all 11 migration files are present; no DocMind revision appears.

- [ ] **Step 9: Commit the reshape**

```bash
git add services/research deploy/prometheus deploy/grafana docs/migration/RESEARCH_FRONTEND_SOURCE.md
git commit -m "chore(research): import service with preserved history"
```

---

### Task 6: Make Service Build Contexts Independent

**Files:**
- Create: `services/knowledge/Dockerfile`
- Modify: `services/research/Dockerfile`
- Modify: `services/research/docker-entrypoint.sh`
- Create: `services/knowledge/.dockerignore`
- Create: `services/research/.dockerignore`
- Create: `tests/architecture/test_service_boundaries.py`

**Interfaces:**
- Consumes: service-local `requirements.txt` and `app` packages.
- Produces: images `evidsight/knowledge:<version>` and `evidsight/research:<version>` built only from their service directories.

- [ ] **Step 1: Write the failing boundary test**

Create `tests/architecture/test_service_boundaries.py`:

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

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3.12 -m pytest tests/architecture/test_service_boundaries.py -v
```

Expected: FAIL because at least one `.dockerignore` does not exist.

- [ ] **Step 3: Normalize Dockerfiles**

Each Dockerfile must use its service directory as build context and contain these equivalent stages:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app
```

Preserve each source image's OS packages and entrypoint behavior. Do not copy from `../../packages` in this task because contracts have no runtime implementation yet.

- [ ] **Step 4: Add deterministic Docker ignores**

Create the same focused `.dockerignore` in both services:

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

- [ ] **Step 5: Run boundary tests and image builds**

```bash
python3.12 -m pytest tests/architecture/test_service_boundaries.py -v
docker build -t evidsight/knowledge:migration services/knowledge
docker build -t evidsight/research:migration services/research
```

Expected: test PASS; both images build without reading files outside their service context.

- [ ] **Step 6: Smoke-import both images**

```bash
docker run --rm --entrypoint python evidsight/knowledge:migration -c "from app.main import app; print(app.title)"
docker run --rm --entrypoint python evidsight/research:migration -c "from app.main import app; print(app.title)"
```

Expected: both commands exit `0` and print their application title.

- [ ] **Step 7: Commit independent build contexts**

```bash
git add services/knowledge services/research tests/architecture/test_service_boundaries.py
git commit -m "build: isolate backend service images"
```

---

### Task 7: Add the 2C2G Compose and Nginx Skeleton

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `deploy/nginx/default.conf`
- Create: `scripts/smoke_compose.sh`
- Create: `tests/architecture/test_compose_contract.py`

**Interfaces:**
- Consumes: service images and frontend build from earlier tasks.
- Produces: a single-host deployment with only Nginx externally exposed; named services and queues matching `docs/ARCHITECTURE.md`.

- [ ] **Step 1: Write the failing Compose contract test**

Create `tests/architecture/test_compose_contract.py`:

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

Install the already-defined root architecture-test dependencies with `python3.12 -m pip install -r requirements-dev.txt`; do not add PyYAML to either service requirements unless the service imports it.

- [ ] **Step 2: Run the contract test to verify it fails**

```bash
python3.12 -m pytest tests/architecture/test_compose_contract.py -v
```

Expected: FAIL because `docker-compose.yml` does not exist.

- [ ] **Step 3: Create Compose with exact service and isolation rules**

Define the eight services from the test. Required settings:

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

Complete the file with health checks, the five named volumes from `docs/ARCHITECTURE.md`, edge/internal networks, service-local environment files, MySQL UTC/utf8mb4 settings, and dependency health conditions. Do not expose backend or data ports.

- [ ] **Step 4: Create Nginx routing**

`deploy/nginx/default.conf` must serve `apps/web/dist`, proxy public Knowledge and Research routes to their APIs, disable proxy buffering for SSE, and reject internal routes:

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

- [ ] **Step 5: Add environment schema and config smoke script**

`.env.example` lists names only for MySQL credentials, JWT settings, service DB URLs, isolated Redis URLs/DBs, Provider keys, image versions and backup paths. It contains no working secret.

Create `scripts/smoke_compose.sh`:

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

- [ ] **Step 6: Run static and runtime verification**

```bash
python3.12 -m pytest tests/architecture/test_compose_contract.py -v
docker compose --env-file .env.test config --quiet
bash scripts/smoke_compose.sh
```

Expected: contract tests PASS; Compose config is valid; both public health checks return 2xx; external Internal API returns `404`; all required containers are healthy.

- [ ] **Step 7: Stop without deleting persistent data**

```bash
docker compose down
```

Do not use `down -v` during ordinary verification.

- [ ] **Step 8: Commit deployment skeleton**

```bash
git add docker-compose.yml .env.example deploy/nginx/default.conf scripts/smoke_compose.sh tests/architecture/test_compose_contract.py
git commit -m "build: add single-node EvidSight deployment"
```

---

### Task 8: Add Cross-Repository Verification and Migration Acceptance

**Files:**
- Modify: `scripts/test_all.sh`
- Create: `tests/architecture/test_repository_layout.py`
- Create: `docs/migration/MIGRATION_ACCEPTANCE.md`
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: all imported service tests, web tests, architecture tests and image builds.
- Produces: one repeatable migration acceptance command and recorded parity evidence.

- [ ] **Step 1: Write the repository layout test**

Create `tests/architecture/test_repository_layout.py`:

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

- [ ] **Step 2: Run layout tests**

```bash
python3.12 -m pytest tests/architecture/test_repository_layout.py tests/architecture/test_service_boundaries.py tests/architecture/test_compose_contract.py -v
```

Expected: PASS.

- [ ] **Step 3: Extend the all-tests runner**

Prepend architecture tests and append the web build to `scripts/test_all.sh`:

```bash
python3.12 -m pytest tests/architecture -v
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
npm --prefix apps/web run build
docker compose config --quiet
```

- [ ] **Step 4: Run complete migration verification**

```bash
bash scripts/verify_source_baselines.sh
bash scripts/test_all.sh
docker build -t evidsight/knowledge:migration services/knowledge
docker build -t evidsight/research:migration services/research
```

Expected: architecture tests, both backend suites, web tests, web build, Compose parsing and both image builds pass.

- [ ] **Step 5: Verify history preservation**

```bash
git log --follow --oneline -- services/knowledge/app/main.py | tail -5
git log --follow --oneline -- apps/web/src/main.js | tail -5
git log --follow --oneline -- services/research/app/main.py | tail -5
```

Expected: each command displays source-project commits older than the EvidSight import commits.

- [ ] **Step 6: Write migration acceptance evidence**

Create `docs/migration/MIGRATION_ACCEPTANCE.md` containing:

- pinned source commits;
- exact commands from Steps 2, 4 and 5;
- observed test counts and outcomes;
- imported Alembic heads and migration counts (`16` Knowledge, `11` Research at the pinned baselines);
- Docker image IDs;
- known source failures or approved deviations;
- confirmation that no business API, state, permission or SSE behavior intentionally changed;
- rollback point: the commit immediately before the first subtree import.

- [ ] **Step 7: Update changelog**

Add a migration entry to `docs/CHANGELOG.md` that links to `MIGRATION_ACCEPTANCE.md` and states only structural outcomes. Do not claim identity unification, Internal Retrieval or frontend research integration is implemented by this plan.

- [ ] **Step 8: Commit acceptance evidence**

```bash
git add scripts/test_all.sh tests/architecture docs/migration/MIGRATION_ACCEPTANCE.md docs/CHANGELOG.md
git commit -m "test: verify monorepo migration parity"
```

---

## Migration Rollback

Before Task 3, record the clean control-plane commit:

```bash
git rev-parse HEAD
```

If an import task fails, preserve diagnostics, fix forward on the import branch, or abandon that unmerged branch. Do not run `git reset --hard` in a worktree containing user changes. Because each subtree import and normalization is committed separately, reviewers can reject one imported unit without discarding the accepted units.

The migration is complete only when Task 8 evidence passes. Source repositories remain writable and authoritative until production data migration, unified frontend, identity integration, deployment rehearsal and rollback rehearsal are separately accepted; this code-layout plan does not authorize archiving them.
