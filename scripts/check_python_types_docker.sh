#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build \
  --target typecheck \
  --tag evidsight-knowledge-typecheck:local \
  "$repo_root/services/knowledge"

docker build \
  --target typecheck \
  --tag evidsight-research-typecheck:local \
  "$repo_root/services/research"

docker run --rm \
  --volume "$repo_root:/workspace:ro" \
  --workdir /workspace \
  --env EVIDSIGHT_MYPY_CACHE_DIR=/tmp/mypy-cache \
  evidsight-knowledge-typecheck:local \
  bash scripts/check_python_types.sh --service knowledge --runner module

docker run --rm \
  --entrypoint bash \
  --volume "$repo_root:/workspace:ro" \
  --workdir /workspace \
  --env EVIDSIGHT_MYPY_CACHE_DIR=/tmp/mypy-cache \
  evidsight-research-typecheck:local \
  scripts/check_python_types.sh --service research --runner module
