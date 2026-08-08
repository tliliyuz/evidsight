#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
required_python="3.12"

if ! command -v uv >/dev/null 2>&1; then
  echo "缺少 uv；请先安装 uv 后重试。" >&2
  exit 2
fi

ensure_service_venv() {
  local service="$1"
  local venv_path="$repo_root/services/$service/.venv"
  local python_path="$venv_path/bin/python"

  if [[ ! -x "$python_path" ]]; then
    uv venv --python "$required_python" "$venv_path"
  fi

  local actual_version
  actual_version="$($python_path -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$actual_version" != "$required_python" ]]; then
    echo "$service .venv 使用 Python $actual_version，要求 Python $required_python。" >&2
    echo "请备份或移除 $venv_path 后重新执行 make setup-python-dev。" >&2
    exit 2
  fi

  uv pip install \
    --python "$python_path" \
    -r "$repo_root/services/$service/requirements-dev.txt"
}

cd "$repo_root"
uv sync --locked --no-install-project
ensure_service_venv knowledge
ensure_service_venv research

echo "Python 开发环境已就绪：root、Knowledge、Research。"
