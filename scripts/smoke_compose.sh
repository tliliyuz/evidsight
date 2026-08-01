#!/usr/bin/env bash
set -euo pipefail

production=false
if [[ "${1:-}" == "--production" ]]; then
  production=true
  shift
fi

npm --prefix apps/web run build

compose=(docker compose)
if [[ "$production" == "true" ]]; then
  compose+=(--file docker-compose.yml --file docker-compose.prod.yml)
fi

"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
curl --fail --retry 20 --retry-delay 3 http://localhost/api/health
curl --fail --retry 20 --retry-delay 3 http://localhost/api/research/health
test "$(curl -sS -o /dev/null -w '%{http_code}' http://localhost/internal/v1/retrieval/search)" = "404"
"${compose[@]}" ps
