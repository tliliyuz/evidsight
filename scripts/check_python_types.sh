#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="all"
runner="venv"
cache_dir="${EVIDSIGHT_MYPY_CACHE_DIR:-.mypy_cache}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      service="${2:-}"
      shift 2
      ;;
    --runner)
      runner="${2:-}"
      shift 2
      ;;
    *)
      echo "未知参数：$1" >&2
      exit 2
      ;;
  esac
done

if [[ "$service" != "all" && "$service" != "knowledge" && "$service" != "research" ]]; then
  echo "--service 只接受 all、knowledge 或 research。" >&2
  exit 2
fi

if [[ "$runner" != "venv" && "$runner" != "module" ]]; then
  echo "--runner 只接受 venv 或 module。" >&2
  exit 2
fi

run_mypy() {
  local service_name="$1"
  shift
  local service_dir="$repo_root/services/$service_name"
  local -a mypy_command

  if [[ "$runner" == "module" ]]; then
    mypy_command=(python -m mypy)
  else
    local mypy_path="$service_dir/.venv/bin/mypy"
    if [[ ! -x "$mypy_path" ]]; then
      echo "缺少 $service_name mypy；请先执行 make setup-python-dev。" >&2
      exit 2
    fi
    mypy_command=("$mypy_path")
  fi

  (
    cd "$service_dir"
    "${mypy_command[@]}" \
      --config-file "$repo_root/pyproject.toml" \
      --cache-dir "$cache_dir" \
      --follow-imports=skip \
      "$@"
  )
}

if [[ "$service" == "all" || "$service" == "knowledge" ]]; then
  run_mypy knowledge \
    app/config.py \
    app/dependencies.py \
    app/api \
    app/middleware \
    app/schemas \
    app/services \
    app/rag \
    app/ingest \
    app/core/permissions.py \
    app/core/csrf.py \
    app/core/exceptions.py \
    app/core/security.py \
    app/core/service_security.py \
    app/core/sse.py \
    app/core/utils.py
fi

if [[ "$service" == "all" || "$service" == "research" ]]; then
  run_mypy research \
    app/config.py \
    app/dependencies.py \
    app/api \
    app/middleware \
    app/schemas \
    app/services \
    app/pipeline \
    app/agent \
    app/tasks \
    app/tools \
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
fi
