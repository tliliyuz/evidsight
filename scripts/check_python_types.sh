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
    app/schemas \
    app/core/permissions.py
)

(
  cd services/research
  .venv/bin/mypy \
    --config-file ../../pyproject.toml \
    app/schemas \
    app/core/permissions.py \
    app/core/utils.py
)
