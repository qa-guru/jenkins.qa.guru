#!/usr/bin/env bash
# Inject microsocks creds for Telegram egress on qa.guru agents.
#
# CLI 6.2.0+ reads config.proxy (undici Socks5ProxyAgent) — no proxychains needed.
# A2 jar still needs proxychains4 (jar SOCKS breaks photo upload).
#
# Usage:
#   prepare-telegram-socks-proxy.sh <config.json>
#       → patch config.proxy.username/password from /opt/qa-guru/etc/microsocks.env
#   prepare-telegram-socks-proxy.sh - <proxychains.conf>
#       → write proxychains conf only (A2 jar; "-" = no JSON). Do not use "" —
#         busybox `sh -xe` drops empty args and the console looks like a one-arg call.
#   prepare-telegram-socks-proxy.sh <config.json> <proxychains.conf>
#       → both (legacy)
set -euo pipefail

CONFIG="${1:-}"
PROXYCHAINS="${2:-}"
if [[ "$CONFIG" == "-" ]]; then
  CONFIG=""
fi
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

if [[ -n "$PROXYCHAINS" ]]; then
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
fi

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
elif [[ -n "$CONFIG" && "$CONFIG" != "" ]]; then
  echo "Missing config file: ${CONFIG}" >&2
  exit 1
fi
