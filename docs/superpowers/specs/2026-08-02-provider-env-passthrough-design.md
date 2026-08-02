# Provider 环境变量透传设计

日期：2026-08-02

## 目标

让本地 Docker Compose 验收能够通过根目录 `.env` 显式配置 LLM、Embedding、Rerank 和 Tavily 的 Base URL 与模型，同时移除 `.env.example` 中当前没有接线、容易误导的占位变量。

## 范围

Knowledge 容器接收以下已有 Settings 变量：

- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_FLASH_MODEL`
- `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`
- `RERANK_BASE_URL`、`RERANK_API_KEY`、`RERANK_MODEL`

Research 容器接收以下已有 Settings 变量：

- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_FLASH_MODEL`
- `TAVILY_BASE_URL`、`TAVILY_API_KEY`

根目录 `.env.example` 为上述变量提供代码当前默认地址和模型的示例值，API Key 继续使用明确占位符。

## 清理项

从 `.env.example` 删除当前 Compose、脚本和服务均未读取的变量：

- `KNOWLEDGE_DATABASE_URL`
- `RESEARCH_DATABASE_URL`
- `EVIDSIGHT_IMAGE_VERSION`
- `BACKUP_PATH`

数据库连接继续由 Compose 注入的 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD` 和 `MYSQL_DATABASE` 组成。本次不引入统一 `EVIDSIGHT_PROVIDER_*` 配置命名，也不增加镜像发布或备份功能。

## 数据流

`.env` 由 Docker Compose 进行变量替换，分别进入 `x-knowledge-environment` 和 `x-research-environment`。Pydantic Settings 使用既有字段读取这些值；未在 `.env` 中覆盖时，Compose 使用与服务 Settings 一致的默认 Base URL 和模型。

## 验证

先扩展 Compose 契约测试，断言每个服务只接收其需要的 Provider 变量，并确认 `.env.example` 不再包含未接线占位符。测试应在 Compose 修改前失败，修改后通过。最后运行全部架构测试以及开发、生产 Compose 配置解析。
