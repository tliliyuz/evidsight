# DEVELOPMENT — EvidSight 开发指南

| 属性 | 值 |
|:---|:---|
| 文档状态 | v1.0 开发基线 |
| 最后更新 | 2026-08-07 |
| 当前阶段 | M3：Research Service 接入内部知识（进行中） |

> 本文定义开发入口、Monorepo 目录职责、环境准备、常用命令和交付门禁。产品行为以 [PRD.md](../specs/PRD.md) 为准，服务边界以 [ARCHITECTURE.md](../specs/ARCHITECTURE.md) 为准。M0 结构迁移、M1 统一身份与权限、M2 Knowledge 稳定化与 Internal Retrieval 均已完成；M3 起的新功能仍须按 SDD 门禁先执行 ADR 检查、再以验收测试观察正确 RED 后进入生产实现。

## 1. 环境要求

| 工具 | 目标版本 | 用途 |
|:---|:---|:---|
| Python | 3.12+ | Knowledge/Research 服务、契约生成和测试 |
| uv | 与根 `uv.lock` 兼容 | 根工具与 Python 环境管理 |
| Node.js | 20+ | Web 构建与测试（Vite；M4 前 Vue，M4 后 React）|
| Docker Engine | 24+ | 服务镜像与本地部署 |
| Docker Compose | v2 | 单机 2C2G 编排基线 |
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
├── resource/prototype/            # 界面原型基线：dark/ 与 light/ 各 20 张，light 为默认主题
├── deploy/                        # Nginx、Prometheus 与 Grafana 编排资产
├── scripts/                       # 全仓测试、配置与 smoke 入口
├── tests/architecture/            # 服务边界与 Compose 契约测试
└── docker-compose.yml             # 单机编排骨架
```

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

## 3. 当前可用命令

```bash
# 安装根工具环境
uv sync --locked

# 安装提交前静态门禁（pre-commit：ruff + 提交信息格式），每个 worktree 初始化时各执行一次
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type commit-msg

# 运行全仓测试
bash scripts/test_all.sh

# Python lint（ruff：静态检查 + 导入排序；不修改文件，只报告）
uvx ruff check services/ scripts/ tests/ packages/contracts/

# Python 格式化一致性检查（--check 不修改文件；正式格式化去掉 --check）
uvx ruff format --check services/ scripts/ tests/ packages/contracts/

# 验证 Compose 配置
docker compose config --quiet

# 检查工作区状态（只读）
git status --short
```

## 4. 本地启动

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
npm --prefix apps/web ci
npm --prefix apps/web run dev
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

测试策略和发布门禁见 [TESTING.md](../specs/TESTING.md)。M0 目标统一入口为：

```bash
python3.12 -m pytest tests/architecture -v
uv run --project services/knowledge pytest
uv run --project services/research pytest
npm --prefix apps/web test
npm --prefix apps/web run build
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
- Web 使用 Vue 3 + TypeScript、组合式 API 和统一 API 客户端；M4 迁向 React + TypeScript 函数组件（[ADR-004](../decisions/ADR-004-web-framework-transition.md)）；
- 时间统一存储为 UTC；
- 日志、Trace、SSE 和错误不得包含密码、Token、服务凭证、完整 Prompt、隐藏推理或内部正文；
- Chat SSE 与 Research SSE 使用独立解析器和状态机；
- Python 代码遵循 ruff 约定（规则集 `E4,E7,E9,F,I`，行宽 100），提交前执行 `ruff check` 与 `ruff format --check`；配置见根 `pyproject.toml` `[tool.ruff]`。ruff 为根开发依赖（`uv add --dev ruff`）：Astral 官方活跃维护，单文件 ~8MB 无传递依赖，覆盖静态检查与格式化，替代方案为 black+isort+flake8 三件套（需三份配置）；
- 提交前静态门禁由 pre-commit 承载（根开发依赖 `uv add --dev pre-commit`，配置 `.pre-commit-config.yaml`）：`ruff check` 与 `ruff format --check` 以 `repo: local` 调用已装 venv 内 ruff（版本随根 uv.lock，不重复固定），`commit-msg` hook 校验提交信息格式。pre-commit 是社区标准 Git Hook 框架（pre-commit org 活跃维护，MIT，约 2MB + cfgv/identify/virtualenv 等小依赖），替代方案为 lefthook（Go 单二进制，需独立配置）或手写 `.git/hooks` 脚本（无法自动管理多语言 hook 环境）。hook 只报告不修改文件，存量 ruff 基线告警按「触碰即清理」增量消解；`pre-commit install` 只对当前 worktree 生效，新增 worktree 需按 §3 重新安装；
- 新依赖必须说明用途、维护状态、体积和替代方案。

## 10. Docker Compose 与运维

M0 目标是单机 2 vCPU / 2 GB RAM 基线。正式 Compose 必须：

- 只由 Nginx 暴露 Web 和 `/api/v1/*`；
- 不对外暴露 `/internal/v1/*`、MySQL、Redis、Chroma 和 `/metrics`；
- Knowledge/Research 使用独立队列和资源限制；
- 默认不常驻完整 Prometheus/Grafana 套件；
- 提供 liveness、readiness 和配置 smoke；
- 停止服务默认保留持久卷。

部署、备份、恢复和故障处理见 [OPERATIONS.md](../specs/OPERATIONS.md)。

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
- [配置规范](../specs/CONFIGURATION.md)
- [运维指南](../specs/OPERATIONS.md)
- [数据迁移与回滚](../specs/DATA_MIGRATION_AND_ROLLBACK.md)
- [变更日志](../CHANGELOG.md)
