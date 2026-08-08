#!/usr/bin/env bash
set -euo pipefail

knowledge_mypy="services/knowledge/.venv/bin/mypy"
research_mypy="services/research/.venv/bin/mypy"

if [[ ! -x "$knowledge_mypy" ]]; then
  echo "缺少 Knowledge mypy；请安装 services/knowledge/requirements-dev.txt" >&2
  exit 2
fi

if [[ ! -x "$research_mypy" ]]; then
  echo "缺少 Research mypy；请安装 services/research/requirements-dev.txt" >&2
  exit 2
fi

(
  cd services/knowledge
  .venv/bin/mypy \
    --config-file ../../pyproject.toml \
    --follow-imports=skip \
    app/config.py \
    app/dependencies.py \
    app/api \
    app/middleware \
    app/schemas \
    app/services \
    app/core/permissions.py \
    app/core/csrf.py \
    app/core/exceptions.py \
    app/core/security.py \
    app/core/service_security.py \
    app/core/sse.py \
    app/core/utils.py
)

(
  cd services/research
  .venv/bin/mypy \
    --config-file ../../pyproject.toml \
    --follow-imports=skip \
    app/config.py \
    app/dependencies.py \
    app/api \
    app/middleware \
    app/schemas \
    app/services \
    app/core/identity_status_client.py \
    app/core/internal_retrieval_client.py \
    app/core/permissions.py \
    app/core/utils.py \
    app/core/exceptions.py \
    app/core/security.py \
    app/core/service_security.py \
    app/core/sse.py \
    app/core/task_state_resolver.py \
    app/core/token_counter.py
)
