#!/usr/bin/env bash
# Shared Jenkins post-build: allure-notifications CLI → Telegram (ADR 008).
# SSOT version: docs/allure-notifications/VERSION → /opt/qa-guru/etc/allure-notifications.version
# Override: ALLURE_NOTIFICATIONS_VERSION=6.0.1|latest
#
# Usage (from job workspace):
#   /opt/qa-guru/bin/send-allure-telegram.sh allure2
#   /opt/qa-guru/bin/send-allure-telegram.sh allure3 [notifications/config.json]
set -euo pipefail

REPORT="${1:-}"
CONFIG="${2:-notifications/config.json}"
VERSION_FILE="${ALLURE_NOTIFICATIONS_VERSION_FILE:-/opt/qa-guru/etc/allure-notifications.version}"

if [[ "$REPORT" != "allure2" && "$REPORT" != "allure3" ]]; then
  echo "usage: $0 allure2|allure3 [config.json]" >&2
  exit 2
fi

cd "${WORKSPACE:-.}"

if [[ "$REPORT" == "allure3" ]]; then
  ALLURE_FOLDER=../allure3/
  if [[ -f allure3/awesome/summary.json ]]; then
    ALLURE_FOLDER=../allure3/awesome/
  elif [[ ! -f allure3/summary.json && ! -f allure3/widgets/summary.json ]]; then
    echo "No Allure summary — skip Telegram notification"
    exit 0
  fi
  sed -i 's|"allureFolder": "[^"]*"|"allureFolder": "'"${ALLURE_FOLDER}"'"|' "$CONFIG"
elif [[ ! -f allure2/widgets/summary.json ]]; then
  echo "No Allure summary — skip Telegram notification"
  exit 0
fi

if [[ -n "${ALLURE_NOTIFICATIONS_VERSION:-}" ]]; then
  VERSION="$ALLURE_NOTIFICATIONS_VERSION"
elif [[ -f "$VERSION_FILE" ]]; then
  VERSION="$(tr -d '[:space:]' <"$VERSION_FILE")"
else
  VERSION=latest
fi
if [[ -z "$VERSION" ]]; then
  VERSION=latest
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node ≥ 20 required for allure-notifications CLI (node missing)"
  exit 1
fi
NODE_MAJOR="$(node -v | sed 's/^v//' | cut -d. -f1)"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  echo "Node ≥ 20 required for allure-notifications CLI (got: $(node -v))"
  exit 1
fi

if ! command -v proxychains4 >/dev/null 2>&1; then
  if command -v apk >/dev/null 2>&1; then
    apk add --no-cache proxychains-ng >/dev/null
  else
    echo "proxychains4 missing (install proxychains-ng on agent)" >&2
    exit 1
  fi
fi

PROXY_IP="$(getent ahostsv4 proxy.qaguru.school | awk 'NR == 1 { print $1; exit }')"
if [[ -z "$PROXY_IP" ]]; then
  echo "Cannot resolve proxy.qaguru.school"
  exit 1
fi
PROXYCHAINS_CONFIG=/tmp/proxychains-telegram.conf
cat >"$PROXYCHAINS_CONFIG" <<EOF
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 ${PROXY_IP} 7777
EOF

echo "allure-notifications@${VERSION} (report=${REPORT}, config=${CONFIG})"
proxychains4 -q -f "$PROXYCHAINS_CONFIG" \
  npx --yes "allure-notifications@${VERSION}" send --config "$CONFIG" --live
echo "Telegram proxy send OK"
