#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${JENKINS_PUBLIC_URL:-https://jenkins.qa.guru}}"
BASE_URL="${BASE_URL%/}"

login_headers="$(curl -sI --max-time 15 "${BASE_URL}/login" || true)"
code="$(printf '%s\n' "$login_headers" | awk 'NR==1 { print $2 }')"
login_loc="$(printf '%s\n' "$login_headers" | awk 'tolower($1)=="location:" { print $2; exit }' | tr -d '\r')"
echo "GET ${BASE_URL}/login → HTTP ${code:-000} Location ${login_loc:-none}"

signup="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/signup" || true)"
echo "GET ${BASE_URL}/signup → HTTP ${signup}"
if [[ "$signup" != "404" ]]; then
  echo "FAIL: expected 404 from /signup after P4 oic-auth, got ${signup}" >&2
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

# P4 SSO-only: /login 302 → commenceLogin unless ?escapeHatch=true (nginx canon 2026-10-10).
if [[ "$code" == "302" ]]; then
  if [[ "$login_loc" != */securityRealm/commenceLogin* ]]; then
    echo "FAIL: /login 302 must target /securityRealm/commenceLogin, got ${login_loc:-none}" >&2
    exit 1
  fi
elif [[ "$code" != "200" && "$code" != "403" ]]; then
  echo "FAIL: expected 200, 302 or 403 from Jenkins login" >&2
  exit 1
fi

echo "OK: Jenkins is reachable"

SMOKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "${SMOKE_DIR}/smoke-allure-jenkins-urls.sh" ]]; then
  "${SMOKE_DIR}/smoke-allure-jenkins-urls.sh" "$BASE_URL"
fi
