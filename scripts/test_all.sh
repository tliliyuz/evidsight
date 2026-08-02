#!/usr/bin/env bash
set -euo pipefail

python3.12 -m pytest tests/architecture -v
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
TAVILY_API_KEY="${TAVILY_API_KEY:-test-tavily-key}" \
  services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
npm --prefix apps/web test
npm --prefix apps/web run build
docker compose config --quiet
