#!/usr/bin/env bash
set -euo pipefail

production=false
if [[ "${1:-}" == "--production" ]]; then
  production=true
  shift
fi

pnpm --dir apps/web run build

compose=(docker compose)
if [[ "$production" == "true" ]]; then
  compose+=(--file docker-compose.yml --file docker-compose.prod.yml)
fi

"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
# nginx 已启用 HTTPS（80 → 443 重定向），冒烟走 https；自签证书用 -k 跳过校验
curl -k --fail --retry 20 --retry-delay 3 https://localhost/api/health
curl -k --fail --retry 20 --retry-delay 3 https://localhost/api/research/health
test "$(curl -k -sS -o /dev/null -w '%{http_code}' https://localhost/internal/v1/retrieval/search)" = "404"
"${compose[@]}" ps
