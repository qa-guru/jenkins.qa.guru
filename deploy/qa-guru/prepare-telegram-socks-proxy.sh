#!/usr/bin/env bash
# Source microsocks creds, write proxychains conf, optionally patch notifications config.json.
#
# Usage:
#   prepare-telegram-socks-proxy.sh [config.json] [proxychains.conf]
# Defaults: no config patch · /tmp/proxychains-telegram.conf
set -euo pipefail

CONFIG="${1:-}"
PROXYCHAINS="${2:-/tmp/proxychains-telegram.conf}"
ENV_FILE="${MICROSOCKS_ENV_FILE:-/opt/qa-guru/etc/microsocks.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} (deploy: dev/scripts/apply-jenkins-ssot.sh agents)" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

: "${MICROSOCKS_USER:?MICROSOCKS_USER missing in ${ENV_FILE}}"
: "${MICROSOCKS_PASS:?MICROSOCKS_PASS missing in ${ENV_FILE}}"

PROXY_IP="$(getent ahostsv4 proxy.qaguru.school | awk 'NR == 1 { print $1; exit }')"
if [[ -z "$PROXY_IP" ]]; then
  echo "Cannot resolve proxy.qaguru.school" >&2
  exit 1
fi

cat >"$PROXYCHAINS" <<EOF
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 ${PROXY_IP} 7777 ${MICROSOCKS_USER} ${MICROSOCKS_PASS}
EOF

if [[ -n "$CONFIG" && -f "$CONFIG" ]]; then
  CONFIG="$CONFIG" node -e '
const fs = require("fs");
const configPath = process.env.CONFIG;
const cfg = JSON.parse(fs.readFileSync(configPath, "utf8"));
if (!cfg.proxy) process.exit(0);
cfg.proxy.username = process.env.MICROSOCKS_USER;
cfg.proxy.password = process.env.MICROSOCKS_PASS;
fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2));
'
fi
