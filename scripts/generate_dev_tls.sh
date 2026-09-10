#!/usr/bin/env bash
# 生成本地开发用自签 TLS 证书（nginx HTTPS 服务块使用）。
#
# 私有密钥绝不提交：产物写入 deploy/secrets/nginx/（git-ignored）。
# 默认 SAN 覆盖 localhost / 127.0.0.1 / ::1；局域网 IP 访问需额外传入：
#   ./scripts/generate_dev_tls.sh --ip 192.168.1.10 --dns my-mac.local
# 已存在时跳过（--force 重新生成）。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$repo_root/deploy/secrets/nginx"
cert="$out_dir/tls.crt"
key="$out_dir/tls.key"

force=false
san_dns=(localhost)
san_ip=(127.0.0.1 ::1)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) force=true; shift ;;
    --dns) san_dns+=("${2:?--dns 需要值}"); shift 2 ;;
    --ip) san_ip+=("${2:?--ip 需要值}"); shift 2 ;;
    *) echo "未知参数：$1（支持 --dns/--ip/--force）" >&2; exit 2 ;;
  esac
done

if [[ "$force" != "true" && -f "$cert" && -f "$key" ]]; then
  echo "证书已存在：$cert（--force 重新生成）"
  exit 0
fi

mkdir -p "$out_dir"

san="DNS:${san_dns[0]}"
for d in "${san_dns[@]:1}"; do san="$san,DNS:$d"; done
for ip in "${san_ip[@]}"; do san="$san,IP:$ip"; done

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$key" -out "$cert" -days 825 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=$san" \
  -addext "extendedKeyUsage=serverAuth" >/dev/null 2>&1

echo "已生成自签证书："
echo "  cert: $cert"
echo "  key : $key"
echo "  SAN : $san"
echo "浏览器首次访问 https://localhost 会提示不受信任（自签），点「高级 → 继续」即可。"
