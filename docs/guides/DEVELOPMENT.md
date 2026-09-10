# DEVELOPMENT — EvidSight 开发指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 开发基线 |
| 最后更新 | 2026-08-09 |
| 当前阶段 | M4：切片 4 继续进行；切片 5 契约门禁已解除 |

> 本文定义开发入口、Monorepo 目录职责、环境准备、常用命令和交付门禁。产品行为以 [PRD.md](../specs/PRD.md) 为准，服务边界以 [ARCHITECTURE.md](../specs/ARCHITECTURE.md) 为准。M0—M3 已完成；M4 已完成 React 工程基线、身份认证、应用壳层、工作台与知识中心。External OpenAPI 现已覆盖 Auth、Knowledge Base、Document、Conversation、Chat、Research、Evidence、Report 与两套 SSE，并由 Knowledge/Research 双 Provider 路由及测试覆盖门禁约束。切片 4 的在途结果继续保留，但其来源卡片到知识切片抽屉的实时鉴权联动和视觉验收尚未完成，不得宣告切片完成；切片 5 开发必须直接消费 OpenAPI，不得根据 Pydantic Model、返回字典或旧迁移信封另立字段契约。

## 1. 环境要求

| 工具 | 目标版本 | 用途 |
|:---|:---|:---|
| Python | 3.12+ | Knowledge/Research 服务、契约生成和测试 |
| uv | 与根 `uv.lock` 兼容 | 根工具与 Python 环境管理 |
| Node.js | 22.13+ | Web 构建与测试；满足 `pnpm 11` 的运行时要求 |
| pnpm | `apps/web/package.json#packageManager` | Web 依赖、脚本与冻结锁文件管理 |
| Docker Engine | 24+ | 服务镜像与本地部署 |
| Docker Compose | v2 | 开发单机全栈与生产三节点编排 |
| MySQL | 8.0+ | `platform_db`、`knowledge_db`、`research_db` |
| Redis | 7.0+ | 队列、锁、租约和短期缓存 |
| Git | 2.39+ | 历史保留迁移与常规协作 |

所有时间使用 UTC；本地显示由客户端按 ISO/RFC 3339 时间转换。密钥和密码只能通过未提交的环境文件或 Secret 注入。

## 2. 项目目录结构

### 2.1 当前仓库

```text
evidsight/
├── AGENTS.md                      # Agent 开发门禁与权威文档矩阵
├── CLAUDE.md                      # 与 AGENTS.md 同步的协作入口
├── README.md                      # 项目入口和当前状态
├── pyproject.toml                 # 当前根工具骨架，不是后端服务依赖集合
├── uv.lock
├── docs/
│   ├── README.md                   # 文档中心与分层规则
│   ├── specs/                     # 项目级权威规范及索引
│   ├── guides/                    # 开发与操作指南
│   ├── plans/                     # 路线图与实施计划
│   ├── CHANGELOG.md
│   └── decisions/                  # 已接受及评审中的重要架构决策
├── packages/
│   └── contracts/
│       └── README.md              # Contract 设计；Schema/Fixture 尚待落地
├── services/
│   ├── knowledge/                 # Knowledge Service 实现、测试、迁移与专项文档
│   └── research/                  # Research Service 实现、测试、迁移与专项文档
├── apps/
│   └── web/                       # M0 迁入的 Vue Web 基线与专项文档
├── resource/prototype/            # 界面原型基线：截图与已跟踪交互参考，light 为默认工作区主题
├── deploy/                        # 生产节点 Compose、Nginx、监控与数据初始化资产
├── scripts/                       # 全仓测试、配置与 smoke 入口
├── tests/architecture/            # 服务边界与 Compose 契约测试
└── docker-compose.yml             # Mac 等开发机的单机全栈入口
```

前端视觉开发只使用 `resource/prototype/reference/evidsight-web/` 的已跟踪交互参考和 `resource/prototype/{light,dark}/` 截图；不得引用 Git 忽略的 `.superpowers/`。参考目录不进入 Vite 构建或部署。

前端切片在 RED/GREEN 节点使用：

```bash
pnpm --dir apps/web check:design-tokens
pnpm --dir apps/web check:visual-baselines
```

页面行为测试与视觉截图测试仍按该切片验收条件执行；完整跨页面 E2E 留在 M4 切片 8，但页面视觉回归不得延后。

### 2.2 后续里程碑目标结构

```text
evidsight/
├── apps/
│   └── web/                       # 唯一 React + TypeScript Web
│       ├── src/
│       ├── tests/
│       ├── package.json
│       └── docs/
├── services/
│   ├── knowledge/                 # FastAPI、Celery、Alembic、Knowledge-owned 数据
│   │   ├── app/
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── docs/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   └── research/                  # Research API、Worker、Beat、Recovery Scanner
│       ├── app/
│       ├── alembic/
│       ├── tests/
│       ├── docs/
│       ├── pyproject.toml
│       └── Dockerfile
├── packages/
│   ├── contracts/                 # Internal Retrieval/Evidence JSON Schema
│   └── api-contracts/             # 外部 OpenAPI 与 SSE data Schema
├── deploy/
│   └── nginx/default.conf
├── docs/
│   ├── README.md
│   ├── specs/
│   ├── guides/
│   ├── plans/
│   ├── decisions/
│   └── CHANGELOG.md
├── scripts/                       # 全仓测试、配置检查、smoke、备份恢复
├── tests/architecture/            # 服务边界、Compose 和目录契约测试
├── docker-compose.yml
└── .env.example
```

目录所有权规则：

- `apps/web` 只消费正式 API/事件，不访问服务数据库或内部模型；
- `services/research` 只通过 `/internal/v1` 和 Contract 使用 Knowledge；
- `services/knowledge` 不依赖 Research Task、Evidence Graph 或报告实现；
- `packages/contracts` 不导入任何服务 `app` 包；
- 根目录只负责规范、编排、契约和跨仓库验证，不合并服务依赖。

### 2.3 新增文件与目录结构门禁

创建或移动代码文件前，必须先按本节目录职责选择所属层和既定物理形态。服务实现只能进入对应服务及其既有模块边界；跨服务能力必须通过正式 API 或 `packages/contracts/`；根目录不得新增绕过现有边界的门面层。无法归类、需要新增顶层目录、改变服务边界或新增公共契约时，先补充对应规范并重新执行 ADR 检查，不得直接创建临时目录或重复抽象；结构边界变化必须同步目录契约测试或等价 smoke。

## 3. 当前可用命令

```bash
# 安装根工具环境
uv sync --locked --no-install-project

# 一次性建立/更新根工具环境与两个 Python 3.12 服务开发环境
# 服务 .venv 按 requirements-dev.lock 的版本与哈希冻结安装，后续检查不临时解析依赖
make setup-python-dev

# 安装提交前静态门禁（ruff + mypy + Web + 提交信息格式），每个 worktree 初始化时各执行一次
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type commit-msg

# 运行全仓测试
bash scripts/test_all.sh

# Python lint（ruff：静态检查 + 导入排序；不修改文件，只报告）
uvx ruff check services/ scripts/ tests/ packages/contracts/

# Python 格式化一致性检查（--check 不修改文件；正式格式化去掉 --check）
uvx ruff format --check services/ scripts/ tests/ packages/contracts/

# 当前 Python 类型门禁（分别使用 Knowledge/Research 独立环境）
make type-check

# 候选版/依赖变更后的 Linux Python 3.12 复核
# 首次或 requirements 变化时构建 typecheck target；后续复用 Docker 层，不在运行容器中 pip install
make type-check-docker

# 本地复现基础 CI 的快速单元、Contract 与 OpenAPI 门禁
make fast-unit
make contracts-ci
make openapi-ci

# 验证开发单机 Compose 配置
docker compose config --quiet

# 检查工作区状态（只读）
git status --short
```

## 4. 本地启动

Mac 的完整 Docker 开发环境继续使用根 Compose，不依赖三台生产云节点。服务 `.venv` 只承载编辑器解析、ruff、mypy、pre-commit 及不依赖 MySQL/Redis/Celery/外部 Provider 的纯单元检查；集成测试、Worker、迁移、smoke 与依赖外部服务的测试一律在 Docker Compose 中执行，不得用本机进程替代：

```bash
# 首次启动前生成本地自签 TLS 证书（nginx HTTPS 用；产物在 deploy/secrets/nginx/，git 忽略）
bash scripts/generate_dev_tls.sh
# 或 make tls-dev；局域网 IP 访问可附加 --ip <局域网IP> 重新生成

docker compose up -d
docker compose ps
```

本机 Web 通过 **`https://localhost`** 访问（nginx 同时提供 80→443 重定向；刷新/退出所需的 `Secure` Cookie 只在 HTTPS 下可用）。首次访问自签证书会有浏览器「不受信任」提示，点「高级 → 继续」即可；局域网 IP 访问需用 `--ip` 重新生成证书并在浏览器接受该地址的自签提示。

本地环境只使用开发卷、开发密钥和 Compose 服务名；不得注入生产私网地址、生产 Secret 或连接生产 MySQL/Redis。停止服务默认保留本地卷。

以下命令使用各服务独立环境；首次运行前先按各自锁文件安装依赖：

```bash
# Knowledge Service
uv sync --project services/knowledge --locked
uv run --project services/knowledge alembic upgrade head
uv run --project services/knowledge uvicorn app.main:app --reload --port 8000

# Research Service
uv sync --project services/research --locked
uv run --project services/research alembic upgrade head
uv run --project services/research uvicorn app.main:app --reload --port 8001

# Web
corepack enable
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web run dev
```

Knowledge 与 Research 必须使用独立虚拟环境、依赖锁、Alembic 配置和数据库账号。不得从根环境偶然导入某个服务的依赖。

## 5. 环境变量与配置

键名、类型、默认值、安全级别和作用服务统一记录在 [CONFIGURATION.md](../specs/CONFIGURATION.md)。基本规则：

- 提交 `.env.example`，不提交 `.env`；
- JWT 签名材料和服务凭证必须可轮换并带 Key ID；
- Knowledge/Research 使用独立数据库 DSN、Redis DB、队列和 Key 前缀；
- 外部 Provider 默认不得接收未经策略允许的内部正文；
- 配置缺失必须使 readiness 或启动明确失败，不回退到不安全默认值。

## 6. 数据库与迁移

- `platform_db` 与 `knowledge_db` 由 Knowledge Service 管理；
- `research_db` 由 Research Service 管理；
- 三条 Alembic 链分别维护 version table；
- 跨数据库稳定 ID 不建立外键；
- Schema 或数据迁移先更新对应 Database 规范；
- 生产数据映射、校验和回滚见 [DATA_MIGRATION_AND_ROLLBACK.md](../specs/DATA_MIGRATION_AND_ROLLBACK.md)。

禁止为了本地便利让 Research 获得 `knowledge_db`、Chroma 或上传目录访问权。

## 7. 测试与验证

测试矩阵和发布门禁见 [测试规范](../specs/TESTING.md)，命令说明与结果记录见 [测试执行指南](TEST_EXECUTION.md)。当前统一入口为：

```bash
python3.12 -m pytest tests/architecture -v
uv run --project services/knowledge pytest
uv run --project services/research pytest
pnpm --dir apps/web run lint
pnpm --dir apps/web run format:check
pnpm --dir apps/web test
pnpm --dir apps/web run build
docker compose config --quiet
```

当前目录尚未全部存在时，应明确报告“未迁入/未验证”，不得跳过后声称全量通过。

## 8. 规范驱动开发流程

所有行为变更遵循 [AGENTS.md](../../AGENTS.md)：

```text
权威规格确认
→ 验收条件和测试场景
→ RED
→ GREEN
→ REFACTOR
→ 受影响模块完整验证
→ CHANGELOG/ADR/权威文档同步
→ 代码审查
```

Markdown 变更先完整阅读 [DOCUMENT_FORMAT.md](DOCUMENT_FORMAT.md) 与 [DOCUMENT_GOVERNANCE.md](DOCUMENT_GOVERNANCE.md)，按唯一权威来源更新；完成后运行 `bash scripts/check-document-format.sh`、必要时运行 `bash scripts/check-adr-governance.sh`，并执行 `git diff --check`。新增、移动或拆分代码文件前先核对本节目录职责和模块边界；新顶层目录、跨服务边界或公共契约必须先更新对应规范并执行 ADR 检查。

变更入口：

| 变更类型 | 先更新 |
|:---|:---|
| 产品范围或验收 | `docs/specs/PRD.md` |
| 服务边界或部署 | `docs/specs/ARCHITECTURE.md`，必要时 ADR |
| 身份、权限、外发 | `docs/specs/IDENTITY_AND_ACCESS.md`，必要时 ADR |
| HTTP/SSE | `docs/specs/API.md` 与 API Contract |
| 跨服务字段 | `packages/contracts/` |
| 数据库 | 对应服务 `docs/DATABASE.md` |
| Pipeline | 对应 Pipeline 文档 |
| 页面和状态机 | `apps/web/docs/FRONTEND.md` |

纯文档变更可以不制造业务 RED，但必须执行 Markdown 链接、术语、Schema 或相关 smoke 检查。

## 9. 编码与安全约定

- 文档、注释和提交信息使用中文；代码标识符使用英文；
- 提交信息 subject 必须使用 `add|fixed|update|refactor: 中文描述`（技术专有名词可保留英文），由 pre-commit 的 `commit-msg` hook（`scripts/check_commit_msg.sh`）强制校验；
- Python IO 使用 async，数据库 Session 依赖注入；
- API 层只校验、鉴权并调用 Service；
- Web 使用 React + TypeScript 函数组件和统一 API 客户端（[ADR-004](../decisions/ADR-004-web-framework-transition.md)）；依赖与脚本统一由 pnpm 管理，ESLint 检查 TypeScript/React，Prettier 统一格式，根 `.editorconfig` 提供编辑器基础约束；
- 时间统一存储为 UTC；
- 日志、Trace、SSE 和错误不得包含密码、Token、服务凭证、完整 Prompt、隐藏推理或内部正文；
- Chat SSE 与 Research SSE 使用独立解析器和状态机；
- Python 代码遵循 ruff 约定（规则集 `E4,E7,E9,F,I`，行宽 100），提交前执行 `ruff check` 与 `ruff format --check`；配置见根 `pyproject.toml` `[tool.ruff]`。ruff 为根开发依赖（`uv add --dev ruff`）：Astral 官方活跃维护，单文件 ~8MB 无传递依赖，覆盖静态检查与格式化，替代方案为 black+isort+flake8 三件套（需三份配置）；
- Python 类型检查使用 mypy，当前强制范围与渐进规则以 [TESTING.md §3.1](../specs/TESTING.md#31-架构与静态边界) 为准。mypy 与 `types-python-jose` 类型桩固定在两个服务各自的 `requirements-dev.txt`，Knowledge 另含 `types-psutil`，随服务依赖解析 Pydantic/FastAPI/SQLAlchemy/JWT/psutil 类型；Research 开发依赖另包含既有异步 SQLite 测试 Fixture 所需的 `aiosqlite`。两个服务以 `requirements-dev.lock` 固定完整版本和制品哈希；为兼容 Intel macOS 与 CI Linux，开发锁将既有传递依赖约束为 `onnxruntime 1.23.x`、`cryptography 46.x`。这些依赖只进入服务 `.venv`、Dockerfile 的 `typecheck` 和独立 `ci-test` 构建 target，不进入默认生产 `runtime` 阶段，生产镜像与运行时体积增量为 0。`make setup-python-dev` 是服务 `.venv` 的唯一初始化入口，固定 Python 3.12 并按哈希锁安装；日常 `make type-check` 和 pre-commit 直接复用该环境，禁止在检查过程中临时解析依赖。`make type-check-docker` 只在首次或 requirements 变化时构建依赖层，运行时以只读工作区挂载复核 Linux Python 3.12，不执行 `pip install`。mypy/Typeshed 生态均活跃维护；Pydantic 启用官方 mypy plugin，SQLAlchemy 不启用已废弃的旧 plugin，ORM 后续扩大范围时使用 SQLAlchemy 2 `Mapped[...]`/`mapped_column()` 原生类型。替代方案为 Pyright（高性能，但官方 CLI 主要由 npm 分发，会把 Python 门禁耦合到现有 Web 包或引入第二个 Node 工程）或仅依赖 ruff/测试（无法检查跨函数类型契约）；
- OpenAPI 基础校验使用根开发依赖 `openapi-spec-validator 0.7.x`（成熟、活跃维护的纯 Python 校验器，连同传递依赖约数 MB），覆盖规范语法与 `$ref`；示例由 `jsonschema` 校验，路由一致性继续由 Provider 契约测试负责。替代方案是自行维护完整 OpenAPI 元模型与引用解析器，维护风险和漏检面更大；
- Knowledge 的全量 Contract/测试门禁另固定 `types-PyYAML` 与 `types-jsonschema`；两者为纯类型桩开发依赖，不进入生产镜像。
- mypy 六批收口已全部完成：① Schema/权限纯函数，② 安全与状态核心，③ 配置/依赖注入/API，④ Service 与跨服务客户端，⑤ Pipeline/任务/Worker，⑥ ORM/脚本/测试/Contract 生成链。最终强制范围见 [TESTING.md §3.1](../specs/TESTING.md#31-架构与静态边界)，新增 Python 文件必须保持零错误。
- 提交前静态门禁由 pre-commit 承载（根开发依赖 `uv add --dev pre-commit`，配置 `.pre-commit-config.yaml`）：Python 执行 ruff 与全量 mypy 类型检查，Web 执行 ESLint/Prettier 检查，`commit-msg` hook 校验提交信息格式。pre-commit 是社区标准 Git Hook 框架（pre-commit org 活跃维护，MIT，约 2MB + cfgv/identify/virtualenv 等小依赖），替代方案为 lefthook（Go 单二进制，需独立配置）或手写 `.git/hooks` 脚本（无法自动管理多语言 hook 环境）。hook 只报告不修改文件；`pre-commit install` 只对当前 worktree 生效，新增 worktree 需按 §3 重新安装；
- pnpm 用于确定性安装和磁盘复用，活跃维护；项目新增的包管理器运行时不进入浏览器产物，替代方案为 npm（当前锁文件与脚本将退出）或 yarn。ESLint、`typescript-eslint`、React Hooks/Refresh 插件用于可执行的 TypeScript/React 静态规则，Prettier 用于确定性格式化；这些均为活跃维护的开发依赖，不进入生产 bundle。替代方案分别为 Biome（单工具但需迁移规则基线）和仅依赖 TypeScript/人工格式审查（覆盖不足且不可重复）；
- 新依赖必须说明用途、维护状态、体积和替代方案。

## 10. Docker Compose 与运维

按 [ADR-011](../decisions/ADR-011-three-node-distributed-deployment.md)，编排入口分为：

| 入口 | 用途 | 组件范围 |
|:---|:---|:---|
| 根 `docker-compose.yml` | Mac 等开发机单机全栈 | 全部核心组件与本地卷 |
| `deploy/compose/cloud-edge.yml` | 生产云节点 1 | Nginx、Web、Research API/Worker/Beat |
| `deploy/compose/cloud-data.yml` | 生产云节点 2 | MySQL、Redis、主备份调度 |
| `deploy/compose/cloud-knowledge.yml` | 生产云节点 3 | Knowledge API/Worker/Beat、uploads、Chroma |

三份生产 Compose 是 M5 目标资产，当前未落地前不得执行或声称三节点部署已实现。实现后必须：

- 只由云节点 1 的 Nginx 暴露 Web 和外部 API；
- 不对公网暴露 `/internal/v1/*`、MySQL、Redis、Knowledge API、Chroma 和 `/metrics`；
- Knowledge/Research 使用独立队列、单 Worker 并发和节点级资源限制；
- Knowledge API/Worker/Beat 与持久卷保持在云节点 3；
- 默认不常驻完整 Prometheus/Grafana/Loki；
- 提供跨节点 liveness、readiness、配置和网络边界 smoke；
- 停止服务默认保留持久卷；
- 与开发环境复用同一不可变镜像和配置 Schema，不复用数据与 Secret。

运行可靠性、备份恢复目标和故障语义见 [RELIABILITY.md](../specs/RELIABILITY.md)；具体部署、备份、恢复和故障操作见 [OPERATIONS.md](OPERATIONS.md)。

## 11. 常用检查

```bash
# 文档中的规划占位
rg -n 'TODO|TBD|待编写|后续建立' docs packages services apps

# 服务边界违规候选
rg -n 'services\.(knowledge|research)\.app|knowledge_db|chroma' services

# 单 KB Chat / 多 KB Research 术语
rg -n '多 KB Chat|多知识库问答|knowledge_base_ids|knowledge_base_id' docs packages services apps

# 文档相对链接由项目文档检查脚本统一验证；脚本在 M0 建立
```

## 12. 相关文档

- [PRD](../specs/PRD.md)
- [总体架构](../specs/ARCHITECTURE.md)
- [路线图](../plans/ROADMAP.md)
- [测试策略](../specs/TESTING.md)
- [测试执行指南](TEST_EXECUTION.md)
- [配置规范](../specs/CONFIGURATION.md)
- [运行可靠性与恢复规范](../specs/RELIABILITY.md)
- [运维操作指南](OPERATIONS.md)
- [数据迁移与回滚](../specs/DATA_MIGRATION_AND_ROLLBACK.md)
- [变更日志](../CHANGELOG.md)
