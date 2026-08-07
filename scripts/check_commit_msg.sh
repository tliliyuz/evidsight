#!/usr/bin/env bash
# 校验提交信息 subject 遵循 AGENTS.md 提交约定：
#   add|fixed|update|refactor: 中文描述（技术专有名词可保留英文）
# 放行 Git 自动生成的 merge/revert/fixup!/squash! 前缀。
set -u

msg_file="${1:-}"
if [[ -z "$msg_file" || ! -f "$msg_file" ]]; then
    echo "usage: check_commit_msg.sh <commit-msg-file>" >&2
    exit 1
fi

subject="$(sed -n '1p' "$msg_file")"

# 放行自动合并与交互式重写前缀
case "$subject" in
    Merge\ *) exit 0 ;;
    merge\ *) exit 0 ;;
    revert:*) exit 0 ;;
    fixup!*) exit 0 ;;
    squash!*) exit 0 ;;
esac

if [[ ! "$subject" =~ ^(add|fixed|update|refactor): ]]; then
    echo "提交信息 subject 必须使用 add|fixed|update|refactor: 中文描述 前缀（AGENTS.md 约定）" >&2
    echo "当前 subject: $subject" >&2
    exit 1
fi

desc="${subject#*:}"
if [[ -z "${desc// /}" ]]; then
    echo "提交信息 subject 缺少描述内容" >&2
    echo "当前 subject: $subject" >&2
    exit 1
fi

# 描述应含中文（技术专有名词可保留英文，故仅要求出现中文；macOS 无 GNU grep -P，用 perl 检测 Han 字块）
if ! printf '%s' "$desc" | perl -CS -e 'exit 1 unless <STDIN> =~ /\p{Han}/'; then
    echo "提交信息 subject 描述应使用中文（AGENTS.md 约定：add|fixed|update|refactor: 中文描述）" >&2
    echo "当前 subject: $subject" >&2
    exit 1
fi

exit 0
