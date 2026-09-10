#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
knowledge_python="$repo_root/services/knowledge/.venv/bin/python"
research_python="$repo_root/services/research/.venv/bin/python"
image_tag="evidsight-knowledge-contract-ci"

if [[ ! -x "$knowledge_python" || ! -x "$research_python" ]]; then
  echo "缺少服务测试环境；请先执行 make setup-python-dev。" >&2
  exit 2
fi

"$knowledge_python" -m pytest "$repo_root/packages/contracts/tests" -v
TAVILY_API_KEY="${TAVILY_API_KEY:-test-tavily-key}" \
  "$research_python" -m pytest \
    -c "$repo_root/services/research/pytest.ini" \
    "$repo_root/services/research/tests/contract"

docker build \
  --target ci-test \
  --tag "$image_tag" \
  "$repo_root/services/knowledge"

docker run --rm \
  --env ENV=testing \
  --env DEBUG=true \
  --env JWT_SECRET_KEY=test-jwt-secret-key-for-ci-only \
  --env REFRESH_TOKEN_SECRET_KEY=test-refresh-secret-key-for-ci-only \
  --volume "$repo_root/packages/contracts:/app/packages/contracts:ro" \
  --workdir /app \
  "$image_tag" \
  python -m pytest -c pytest.ini \
    tests/contract/test_identity_status_provider.py \
    tests/contract/test_retrieval_provider.py \
    tests/contract/test_retrieval_endpoints.py
