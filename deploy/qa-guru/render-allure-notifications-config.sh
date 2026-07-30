#!/usr/bin/env bash
# Render notifications/config.json from the shared template — Jenkins build step (ADR 010).
# Single place where the Allure report URL contract is built:
#   allure3 → ${BUILD_URL}<report>/awesome/index.html   (report dir layout: awesome/ + dashboard/)
#   allure2 → ${BUILD_URL}<report>/index.html
# Runs as a *build* step so credential bindings (${TELEGRAM_*}) are in the environment
# and the config exists even when the test step fails.
#
# Usage (from job workspace):
#   /opt/qa-guru/bin/render-allure-notifications-config.sh allure3 \
#     --results tests/build/allure-results \
#     --comment "Allure 3 · freestyle" \
#     --testops https://allure.qa.guru/project/5274
set -euo pipefail

FLAVOR="${1:-}"
shift || true

case "$FLAVOR" in
  allure2 | allure3) ;;
  *)
    echo "usage: $0 allure2|allure3 [--report <dir>] [--results <dir>] [--comment <text>]" \
      "[--environment <name>] [--language ru|en] [--testops <url>] [--out <path>]" >&2
    exit 2
    ;;
esac

REPORT_DIR="$FLAVOR"
RESULTS_DIR=""
COMMENT=""
ENVIRONMENT="reference_prod"
LANGUAGE="ru"
TESTOPS_URL=""
OUT="notifications/config.json"
TEMPLATE_DIR="${ALLURE_NOTIFICATIONS_TEMPLATE_DIR:-/opt/qa-guru/etc/allure-notifications}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --report) REPORT_DIR="$2"; shift 2 ;;
    --results) RESULTS_DIR="$2"; shift 2 ;;
    --comment) COMMENT="$2"; shift 2 ;;
    --environment) ENVIRONMENT="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --testops) TESTOPS_URL="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --template-dir) TEMPLATE_DIR="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

cd "${WORKSPACE:-.}"

TEMPLATE="${TEMPLATE_DIR}/${FLAVOR}.json.tmpl"
if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing template ${TEMPLATE} (deploy: dev/scripts/apply-jenkins-ssot.sh telegram)" >&2
  exit 1
fi

BUILD_URL="${BUILD_URL:-}"
if [[ -z "$BUILD_URL" ]]; then
  echo "BUILD_URL is empty — run from a Jenkins build step" >&2
  exit 1
fi
[[ "$BUILD_URL" == */ ]] || BUILD_URL="${BUILD_URL}/"

REPORT_DIR="${REPORT_DIR#/}"
REPORT_DIR="${REPORT_DIR%/}"
RESULTS_DIR="${RESULTS_DIR#/}"
RESULTS_DIR="${RESULTS_DIR%/}"

# URL contract + folder layout (see ADR 010).
if [[ "$FLAVOR" == "allure3" ]]; then
  REPORT_URL="${BUILD_URL}${REPORT_DIR}/awesome/index.html"
  # CLI resolves config paths relative to the config file (notifications/).
  ALLURE_FOLDER="../${REPORT_DIR}/awesome/"
  ALLURE_RESULTS_FOLDER="../${RESULTS_DIR}/"
  if [[ -z "$RESULTS_DIR" ]]; then
    echo "--results is required for allure3 (allure-results dir, workspace-relative)" >&2
    exit 2
  fi
  if [[ -z "$TESTOPS_URL" ]]; then
    echo "--testops is required for allure3 (report links block)" >&2
    exit 2
  fi
else
  REPORT_URL="${BUILD_URL}${REPORT_DIR}/index.html"
  # Jar resolves allureFolder relative to CWD (= workspace).
  ALLURE_FOLDER="${REPORT_DIR}"
  ALLURE_RESULTS_FOLDER=""
fi

json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

V_PROJECT="$(json_escape "${JOB_BASE_NAME:-${JOB_NAME:-jenkins}}")"
V_ENVIRONMENT="$(json_escape "$ENVIRONMENT")"
V_COMMENT="$(json_escape "$COMMENT")"
V_LANGUAGE="$(json_escape "$LANGUAGE")"
V_ALLURE_FOLDER="$(json_escape "$ALLURE_FOLDER")"
V_ALLURE_RESULTS_FOLDER="$(json_escape "$ALLURE_RESULTS_FOLDER")"
V_REPORT_URL="$(json_escape "$REPORT_URL")"
V_BUILD_URL="$(json_escape "$BUILD_URL")"
V_TESTOPS_URL="$(json_escape "$TESTOPS_URL")"
V_TOKEN="$(json_escape "${TELEGRAM_BOT_TOKEN:-}")"
V_CHAT="$(json_escape "${TELEGRAM_CHAT_ID:-}")"
V_TOPIC="$(json_escape "${TELEGRAM_TOPIC_ID:-}")"

substitute() {
  local line="$1"
  line="${line//\$\{PROJECT\}/$V_PROJECT}"
  line="${line//\$\{ENVIRONMENT\}/$V_ENVIRONMENT}"
  line="${line//\$\{COMMENT\}/$V_COMMENT}"
  line="${line//\$\{LANGUAGE\}/$V_LANGUAGE}"
  line="${line//\$\{ALLURE_FOLDER\}/$V_ALLURE_FOLDER}"
  line="${line//\$\{ALLURE_RESULTS_FOLDER\}/$V_ALLURE_RESULTS_FOLDER}"
  line="${line//\$\{REPORT_URL\}/$V_REPORT_URL}"
  line="${line//\$\{BUILD_URL\}/$V_BUILD_URL}"
  line="${line//\$\{TESTOPS_URL\}/$V_TESTOPS_URL}"
  line="${line//\$\{TELEGRAM_BOT_TOKEN\}/$V_TOKEN}"
  line="${line//\$\{TELEGRAM_CHAT_ID\}/$V_CHAT}"
  line="${line//\$\{TELEGRAM_TOPIC_ID\}/$V_TOPIC}"
  printf '%s\n' "$line"
}

mkdir -p "$(dirname "$OUT")"
: >"$OUT"
while IFS= read -r line || [[ -n "$line" ]]; do
  # Optional keys: drop the line instead of emitting an empty value.
  if [[ "$line" == *'"topic"'* && -z "${TELEGRAM_TOPIC_ID:-}" ]]; then
    continue
  fi
  substitute "$line" >>"$OUT"
done <"$TEMPLATE"

if grep -q '\${' "$OUT"; then
  echo "Unresolved placeholders in ${OUT}:" >&2
  grep -n '\${' "$OUT" >&2
  exit 1
fi

echo "notifications config: ${OUT} (flavor=${FLAVOR}, report=${REPORT_DIR}, link=${REPORT_URL})"
