#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root_python="$repo_root/.venv/bin/python"
image_tag="evidsight-knowledge-openapi-ci"

if [[ ! -x "$root_python" ]]; then
  echo "缺少根开发环境；请先执行 uv sync --locked --no-install-project。" >&2
  exit 2
fi

"$root_python" "$repo_root/scripts/check_openapi.py" \
  "$repo_root/docs/openapi/evidsight-v1.yaml" \
  --baseline-ref "${OPENAPI_BASE_REF:-}"

docker build \
  --target ci-test \
  --tag "$image_tag" \
  "$repo_root/services/knowledge"

docker run --rm \
  --env ENV=testing \
  --env DEBUG=true \
  --env JWT_SECRET_KEY=test-jwt-secret-key-for-ci-only \
  --env REFRESH_TOKEN_SECRET_KEY=test-refresh-secret-key-for-ci-only \
  --volume "$repo_root/docs/openapi:/app/docs/openapi:ro" \
  --volume "$repo_root/packages/contracts:/app/packages/contracts:ro" \
  --workdir /app \
  "$image_tag" \
  python -m pytest -c pytest.ini \
    tests/contract/test_openapi_consistency.py \
    tests/contract/test_knowledge_v1_api.py \
    tests/contract/test_document_v1_api.py \
    tests/contract/test_conversation_v1_api.py
