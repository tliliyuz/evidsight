#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_knowledge() {
  local python_path="$repo_root/services/knowledge/.venv/bin/python"
  if [[ ! -x "$python_path" ]]; then
    echo "缺少 Knowledge 测试环境；请先执行 make setup-python-dev。" >&2
    exit 2
  fi
  # 两个文件使用真实 Knowledge db_session，按集成测试边界留在 Compose 候选版门禁。
  "$python_path" -m pytest \
    -c "$repo_root/services/knowledge/pytest.ini" \
    --ignore="$repo_root/services/knowledge/tests/unit/core/test_models.py" \
    --ignore="$repo_root/services/knowledge/tests/unit/services/test_kb_list_visible.py" \
    "$repo_root/services/knowledge/tests/unit/core" \
    "$repo_root/services/knowledge/tests/unit/schemas" \
    "$repo_root/services/knowledge/tests/unit/services"
}

run_research() {
  local python_path="$repo_root/services/research/.venv/bin/python"
  if [[ ! -x "$python_path" ]]; then
    echo "缺少 Research 测试环境；请先执行 make setup-python-dev。" >&2
    exit 2
  fi
  TAVILY_API_KEY="${TAVILY_API_KEY:-test-tavily-key}" \
    "$python_path" -m pytest \
      -c "$repo_root/services/research/pytest.ini" \
      "$repo_root/services/research/tests/unit/core" \
      "$repo_root/services/research/tests/unit/schemas" \
      "$repo_root/services/research/tests/unit/services"
}

case "${1:-all}" in
  all)
    run_knowledge
    run_research
    ;;
  knowledge)
    run_knowledge
    ;;
  research)
    run_research
    ;;
  *)
    echo "用法：bash scripts/test_fast_unit.sh [all|knowledge|research]" >&2
    exit 2
    ;;
esac
