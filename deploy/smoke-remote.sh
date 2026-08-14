#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${JENKINS_PUBLIC_URL:-https://jenkins.qa.guru}}"
BASE_URL="${BASE_URL%/}"

code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/login" || true)"
echo "GET ${BASE_URL}/login → HTTP ${code}"

signup="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/signup" || true)"
echo "GET ${BASE_URL}/signup → HTTP ${signup}"
if [[ "$signup" != "200" && "$signup" != "404" ]]; then
  echo "FAIL: expected 200 (open) or 404 (locked) from /signup, got ${signup}" >&2
  exit 1
fi

legacy_headers="$(curl -sI --max-time 15 https://jenkins.autotests.cloud/ || true)"
legacy_code="$(printf '%s\n' "$legacy_headers" | awk 'NR==1 { print $2 }')"
legacy_loc="$(printf '%s\n' "$legacy_headers" | awk 'tolower($1)=="location:" { print $2; exit }' | tr -d '\r')"
echo "GET https://jenkins.autotests.cloud/ → HTTP ${legacy_code:-000} Location ${legacy_loc:-none}"
if [[ "$legacy_code" != "301" || "$legacy_loc" != https://jenkins.qa.guru/ ]]; then
  echo "FAIL: expected 301 Location https://jenkins.qa.guru/ from jenkins.autotests.cloud" >&2
  exit 1
fi

if [[ "$code" != "200" && "$code" != "403" ]]; then
  echo "FAIL: expected 200 or 403 from Jenkins login" >&2
  exit 1
fi

echo "OK: Jenkins is reachable"

SMOKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "${SMOKE_DIR}/smoke-allure-jenkins-urls.sh" ]]; then
  "${SMOKE_DIR}/smoke-allure-jenkins-urls.sh" "$BASE_URL"
fi
