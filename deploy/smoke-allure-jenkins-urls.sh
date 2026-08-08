#!/usr/bin/env bash
# Allure report URL contract on jenkins.qa.guru (ADR 010).
#
# Contract: every published link ends with index.html.
#   single A3 → <build>/allure/awesome|dashboard/index.html
#   dual A3   → <build>/allure3/awesome|dashboard/index.html
#   single A2 → <build>/allure/index.html
#   dual A2   → <build>/allure2/index.html
# Directory URLs (…/awesome/) must 301 to index.html — nginx defense-in-depth for
# in-report navigation; allure-jenkins-plugin itself answers 500 there.
set -euo pipefail

BASE_URL="${1:-${JENKINS_PUBLIC_URL:-https://jenkins.qa.guru}}"
BASE_URL="${BASE_URL%/}"

# job:url-slug  — slug is Jenkins action URL (/allure classic, /allure3 dual-only)
ALLURE3_JOBS=(
  reference-app-tests-freestyle-java-allure3:allure
  reference-app-tests-freestyle-java-allure3-full-attachments:allure
  reference-app-tests-freestyle-js-allure3:allure
  reference-app-tests-freestyle-python-allure3:allure
  reference-app-tests-freestyle-java-allure2-allure3:allure3
)

# job:report-url-slug:permalink[:trend]  — trend=no skips the job-level URL.
ALLURE2_JOBS=(
  reference-app-tests-freestyle-java-allure2:allure:lastSuccessfulBuild:trend
  reference-app-tests-freestyle-js-allure2:allure:lastSuccessfulBuild:trend
  reference-app-tests-freestyle-python-allure2:allure:lastSuccessfulBuild:trend
  reference-app-tests-freestyle-java-allure2-allure3:allure2:lastSuccessfulBuild:trend
  # Student job: suite is red and the last green build predates report archiving —
  # only the link contract of the latest build is asserted.
  41_MashaSelyanko_proect1:allure:lastCompletedBuild:no-trend
)

fail=0

check_url() {
  local label="$1" url="$2" tmp code
  tmp="$(mktemp)"
  code="$(curl -sL -o "$tmp" -w '%{http_code}' "$url" || echo 000)"
  if [[ "$code" != "200" ]]; then
    echo "FAIL [$code] $label → $url" >&2
    fail=1
  elif grep -q "Oops!" "$tmp" 2>/dev/null; then
    echo "FAIL [oops] $label → $url" >&2
    fail=1
  else
    echo "OK  [$code] $label"
  fi
  rm -f "$tmp"
}

check_redirect() {
  local label="$1" url="$2" code target
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || echo 000)"
  target="$(curl -s -o /dev/null -w '%{redirect_url}' "$url" || true)"
  if [[ "$code" == "301" && "$target" == *"/index.html" ]]; then
    echo "OK  [301] $label → index.html"
  else
    echo "FAIL [$code] $label → ${target:-no redirect} ($url)" >&2
    fail=1
  fi
}

for entry in "${ALLURE3_JOBS[@]}"; do
  IFS=: read -r job slug <<<"$entry"
  for view in awesome dashboard; do
    check_url "${job} trend ${view}" "${BASE_URL}/job/${job}/${slug}/${view}/index.html"
    check_url "${job} lastSuccessfulBuild ${view}" \
      "${BASE_URL}/job/${job}/lastSuccessfulBuild/${slug}/${view}/index.html"
  done
  check_redirect "${job} awesome/ dir" "${BASE_URL}/job/${job}/${slug}/awesome/"
done

for entry in "${ALLURE2_JOBS[@]}"; do
  IFS=: read -r job report permalink trend <<<"$entry"
  if [[ "$trend" == "trend" ]]; then
    check_url "${job} trend ${report}" "${BASE_URL}/job/${job}/${report}/index.html"
  fi
  check_url "${job} ${permalink} ${report}" \
    "${BASE_URL}/job/${job}/${permalink}/${report}/index.html"
done

if [[ "$fail" -ne 0 ]]; then
  echo "FAIL: Allure Jenkins URL smoke" >&2
  exit 1
fi

echo "OK: Allure Jenkins URL smoke"
