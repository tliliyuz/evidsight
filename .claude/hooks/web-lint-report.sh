#!/usr/bin/env bash
# Claude Code PostToolUse hook：编辑/写入前端源码后，报告 eslint/prettier 改动预览。
# 只报告不落盘；写入需用户在权限弹窗中对前端格式化/lint 命令批准。
set -uo pipefail

input_file="${1:-}"
if [[ -z "$input_file" || ! -f "$input_file" ]]; then
  exit 0
fi

# 从 hook JSON 提取 file_path（使用 python3，避免 macOS grep -P 依赖）
file_path="$(python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
tool_input = data.get('tool_input') or {}
print(tool_input.get('file_path') or '')
" "$input_file" 2>/dev/null)"

if [[ -z "$file_path" ]]; then
  exit 0
fi

# 只处理 apps/web 前端源码（扩展名匹配含嵌套路径）
case "$file_path" in
  *.ts|*.tsx|*.js|*.jsx|*.css) ;;
  *) exit 0 ;;
esac
case "$file_path" in
  apps/web/*) ;;
  *) exit 0 ;;
esac

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# 工具就绪：pnpm 可用或 node_modules 已装
if ! command -v pnpm >/dev/null 2>&1 && [[ ! -x apps/web/node_modules/.bin/eslint ]]; then
  exit 0
fi

# pnpm --dir apps/web exec 的 cwd 为 apps/web，需用相对路径
rel="${file_path#apps/web/}"

eslint_diff=""
case "$rel" in
  *.ts|*.tsx|*.js|*.jsx)
    eslint_diff="$(pnpm --dir apps/web exec eslint --fix-dry-run "$rel" 2>&1 || true)"
    ;;
esac
prettier_diff="$(diff -u "$file_path" <(pnpm --dir apps/web exec prettier "$rel" 2>/dev/null) 2>/dev/null || true)"

if [[ -z "$eslint_diff" && -z "$prettier_diff" ]]; then
  exit 0
fi

echo ""
echo "══ web lint 报告（未落盘，批准后才写入）══"
if [[ -n "$eslint_diff" ]]; then
  echo "── ESLint（eslint --fix-dry-run，只读）──"
  echo "$eslint_diff"
fi
if [[ -n "$prettier_diff" ]]; then
  echo "── Prettier 格式改动（与当前文件 diff）──"
  echo "$prettier_diff"
fi
echo "批准方式：执行 \`pnpm --dir apps/web run format\` / \`pnpm --dir apps/web exec eslint --fix <file>\` 时在权限弹窗中允许。"
echo ""
