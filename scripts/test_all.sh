#!/usr/bin/env bash
set -euo pipefail

python3.12 -m pytest tests/architecture -v
bash scripts/check_python_types.sh
services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests "$@"
TAVILY_API_KEY="${TAVILY_API_KEY:-test-tavily-key}" \
  services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests "$@"
pnpm --dir apps/web run lint
pnpm --dir apps/web run format:check
pnpm --dir apps/web test
pnpm --dir apps/web run build
docker compose config --quiet
