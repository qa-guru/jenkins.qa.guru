#!/usr/bin/env bash
# Shared Jenkins post-build → Telegram (ADR 008, URL contract ADR 010).
# allure2: jar pin from docs/allure-notifications/JAR-A2-VERSION (4.x A2 pie + text).
# allure3: CLI pin from docs/allure-notifications/VERSION (6.x A3 collage).
#
# Egress is config.proxy in notifications/config.json (socks5 host/port).
# This script does not wrap java/npx with proxychains and does not patch the JSON.
#
# The config comes from the Create/Update Text File build step (notifications/config.json).
#
# Agent helper / bake. Most freestyle jobs inline java -jar (A2) / npx send (A3) for students.
# Exception (demo contrast): autotests-ai-multistack-tests-freestyle-java-allure2-allure3-sh still calls this.
#
# Usage (from workspace, optional):
#   /opt/qa-guru/bin/send-allure-telegram.sh allure2
#   /opt/qa-guru/bin/send-allure-telegram.sh allure3 [notifications/config.json]
set -euo pipefail

REPORT="${1:-}"
CONFIG="${2:-notifications/config.json}"
VERSION_FILE="${ALLURE_NOTIFICATIONS_VERSION_FILE:-/opt/qa-guru/etc/allure-notifications.version}"
JAR_VERSION_FILE="${ALLURE_NOTIFICATIONS_JAR_VERSION_FILE:-/opt/qa-guru/etc/allure-notifications-jar-a2.version}"
if [[ -n "${ALLURE_NOTIFICATIONS_JAR_VERSION:-}" ]]; then
  JAR_VERSION="$ALLURE_NOTIFICATIONS_JAR_VERSION"
elif [[ -f "$JAR_VERSION_FILE" ]]; then
  JAR_VERSION="$(tr -d '[:space:]' <"$JAR_VERSION_FILE")"
else
  JAR_VERSION=4.11.0
fi

if [[ "$REPORT" != "allure2" && "$REPORT" != "allure3" ]]; then
  echo "usage: $0 allure2|allure3 [config.json]" >&2
  exit 2
fi

cd "${WORKSPACE:-.}"

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing ${CONFIG} — add Create/Update Text File → notifications/config.json build step" >&2
  exit 1
fi

# Report folder is owned by the rendered config; here it is read-only input.
ALLURE_FOLDER="$(sed -n 's/.*"allureFolder"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -1)"
if [[ -z "$ALLURE_FOLDER" ]]; then
  echo "No allureFolder in ${CONFIG}" >&2
  exit 1
fi
# CLI paths are relative to the config dir (notifications/), jar paths to the workspace.
REPORT_PATH="${ALLURE_FOLDER#../}"
REPORT_PATH="${REPORT_PATH%/}"
if [[ "$REPORT" == "allure3" ]]; then
  SUMMARY="${REPORT_PATH}/summary.json"
else
  SUMMARY="${REPORT_PATH}/widgets/summary.json"
fi

if [[ ! -f "$SUMMARY" ]]; then
  echo "No Allure summary at ${SUMMARY} — skip Telegram notification"
  exit 0
fi

send_with_retry() {
  local n=0
  until "$@"; do
    n=$((n + 1))
    if [[ "$n" -ge 3 ]]; then
      echo "Telegram send failed after 3 attempts" >&2
      exit 1
    fi
    echo "Telegram send attempt ${n} failed, retry in 2s"
    sleep 2
  done
}

# --- allure2: jar (4.x) — SOCKS from config.proxy ---
if [[ "$REPORT" == "allure2" ]]; then
  JAR="allure-notifications-${JAR_VERSION}.jar"
  if [[ ! -f "$JAR" ]]; then
    if ! curl -fsSL -o "$JAR" \
      "https://github.com/qa-guru/allure-notifications/releases/download/${JAR_VERSION}/${JAR}"; then
      curl -fsSL -o "$JAR" \
        "https://github.com/qa-guru/allure-notifications/releases/download/v${JAR_VERSION}/${JAR}"
    fi
  fi
  echo "allure-notifications jar ${JAR_VERSION} (report=${REPORT}, folder=${ALLURE_FOLDER}, config=${CONFIG})"
  send_with_retry java -DconfigFile="${CONFIG}" -jar "$JAR"
  echo "Telegram send OK"
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
  echo "Node ≥ 26 required for allure-notifications CLI (node missing)"
  exit 1
fi
NODE_MAJOR="$(node -v | sed 's/^v//' | cut -d. -f1)"
if [[ "$NODE_MAJOR" -lt 26 ]]; then
  echo "Node ≥ 26 required for allure-notifications CLI (got: $(node -v))"
  exit 1
fi

echo "@qa-guru/allure-notifications@${VERSION} (report=${REPORT}, folder=${ALLURE_FOLDER}, config=${CONFIG})"
send_with_retry npx --yes --package "@qa-guru/allure-notifications@${VERSION}" -- \
  allure-notifications send --config "$CONFIG" --live
echo "Telegram send OK"
