#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${JENKINS_PUBLIC_URL:-https://jenkins.qa.guru}}"
BASE_URL="${BASE_URL%/}"

code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/login" || true)"
echo "GET ${BASE_URL}/login → HTTP ${code}"

if [[ "$code" != "200" && "$code" != "403" ]]; then
  echo "FAIL: expected 200 or 403 from Jenkins login" >&2
  exit 1
fi

echo "OK: Jenkins is reachable"
