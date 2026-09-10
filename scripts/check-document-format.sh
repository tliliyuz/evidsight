#!/usr/bin/env bash
set -euo pipefail

mode=changed
case "${1:-}" in
  "") ;;
  --changed|--staged|--all) mode="${1#--}" ;;
  *) echo "用法：$0 [--changed|--staged|--all]" >&2; exit 2 ;;
esac

declare -a files=()
case "$mode" in
  all)
    while IFS= read -r path; do [[ -n "$path" ]] && files+=("$path"); done < <(rg --files -g '*.md' | sort)
    ;;
  staged)
    while IFS= read -r path; do [[ -n "$path" ]] && files+=("$path"); done < <(git diff --cached --name-only --diff-filter=ACMR -- '*.md' | sort -u)
    ;;
  changed)
    while IFS= read -r path; do [[ -n "$path" ]] && files+=("$path"); done < <(
      {
        git diff --name-only --diff-filter=ACMR -- '*.md'
        git ls-files --others --exclude-standard -- '*.md'
      } | sort -u
    )
    ;;
esac

if ((${#files[@]} == 0)); then
  echo "文档格式检查：$mode 模式没有待检查的 Markdown。"
  exit 0
fi

fail=0
for file in "${files[@]}"; do
  [[ -f "$file" ]] || continue

  if grep -n $'\t' "$file" >/dev/null; then
    echo "[FAIL] ${file}：包含 Tab 字符"
    fail=1
  fi
  if grep -n '[^[:print:][:space:]]' "$file" >/dev/null; then
    echo "[FAIL] ${file}：包含不可见控制字符"
    fail=1
  fi

  h1_count=$(awk '/^```/{f=!f; next} !f && /^# [^#]/{c++} END{print c+0}' "$file")
  if [[ "$h1_count" != 1 ]]; then
    echo "[FAIL] ${file}：H1 数量为 ${h1_count}，应为 1"
    fail=1
  fi

  if awk '/^```/{f=!f; next} !f && /^[[:space:]]*\*\*[^*]+\*\*[：:]?[[:space:]]*$/{bad=1} END{exit bad ? 1 : 0}' "$file"; then :; else
    echo "[FAIL] ${file}：使用加粗段首模拟标题"
    fail=1
  fi

  if awk '
    /^```/{f=!f; next}
    !f && /^#{1,6} / {
      level=length($1)
      if (previous && level > previous + 1) { bad=1 }
      previous=level
    }
    END { exit bad ? 1 : 0 }
  ' "$file"; then :; else
    echo "[FAIL] ${file}：标题层级跳跃"
    fail=1
  fi

  case "$file" in
    docs/guides/*.md|docs/specs/*.md|services/*/docs/*.md|apps/web/docs/*.md)
      [[ "$file" == *IMPLEMENTATION_LOG.md ]] && continue
      if grep -qE '^## [0-9]+\.' "$file"; then
        if awk '
          /^```/{f=!f; next}
          !f && /^## [0-9]+\./ {
            n=$2; sub(/\..*/, "", n)
            expected++
            if (n != expected) { bad=1 }
          }
          END { exit bad ? 1 : 0 }
        ' "$file"; then :; else
          echo "[FAIL] ${file}：H2 编号不连续"
          fail=1
        fi
      fi
      ;;
  esac
done

if ! cmp -s AGENTS.md CLAUDE.md; then
  echo "[FAIL] AGENTS.md 与 CLAUDE.md 不一致"
  fail=1
fi

if ((fail)); then
  exit 1
fi
echo "文档格式检查通过：$mode 模式，共 ${#files[@]} 个 Markdown。"
