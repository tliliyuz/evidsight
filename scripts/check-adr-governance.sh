#!/usr/bin/env bash
set -euo pipefail

index=docs/decisions/README.md
[[ -f "$index" ]] || { echo "[FAIL] 缺少 $index" >&2; exit 1; }

current=$(sed -n '/^## 当前有效决策索引$/,/^## 历史记录（非当前权威）$/p' "$index" | grep -oE 'ADR-[0-9]{3}-[^)]*\.md' | sort -u || true)
history=$(sed -n '/^## 历史记录（非当前权威）$/,$p' "$index" | grep -oE 'ADR-[0-9]{3}-[^)]*\.md' | sort -u || true)

fail=0
if ! grep -qF 'DOCUMENT_FORMAT.md' "$index"; then
  echo "[FAIL] ADR 索引未引用 DOCUMENT_FORMAT.md"
  fail=1
fi
if ! grep -qF '## 当前有效决策索引' "$index" || ! grep -qF '## 历史记录（非当前权威）' "$index"; then
  echo "[FAIL] ADR 索引缺少当前/历史分区"
  fail=1
fi

while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  name=${file##*/}
  in_current=0
  in_history=0
  grep -Fq "$name" <<<"$current" && in_current=1
  grep -Fq "$name" <<<"$history" && in_history=1
  if ((in_current + in_history != 1)); then
    echo "[FAIL] ${file}：必须恰好出现在当前或历史索引一次"
    fail=1
  fi

  status=$(sed -nE 's/^- 状态：([^[:space:]]+).*$/\1/p; s/^\| 状态 \|[[:space:]]*([^|]+).*$/\1/p' "$file" | head -n1 | tr -d '[:space:]')
  case "$status" in
    proposed|accepted|deprecated)
      if ((in_current != 1)); then
        echo "[FAIL] ${file}：状态 ${status} 必须在当前索引"
        fail=1
      fi
      ;;
    superseded)
      if ((in_history != 1)); then
        echo "[FAIL] ${file}：superseded 必须在历史索引"
        fail=1
      fi
      ;;
    *)
      echo "[FAIL] ${file}：无法识别 ADR 状态 '${status}'"
      fail=1
      ;;
  esac
done < <(rg --files docs/decisions -g 'ADR-[0-9][0-9][0-9]-*.md' | sort)

while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  if ! rg --files docs/decisions -g "$name" | grep -q .; then
    echo "[FAIL] 索引链接不存在：$name"
    fail=1
  fi
done < <(printf '%s\n%s\n' "$current" "$history" | sed '/^$/d' | sort -u)

if ! cmp -s AGENTS.md CLAUDE.md; then
  echo "[FAIL] AGENTS.md 与 CLAUDE.md 不一致"
  fail=1
fi

if ((fail)); then
  exit 1
fi
echo "ADR 治理检查通过。"
