#!/usr/bin/env bash
# Allure 3 CLI wrapper for Multistack @qa-guru/allure-report-kit soft-forks.
# Linked over `allure` on PATH (java/js: /opt/node/bin/allure; python: /usr/local/bin/allure).
set -euo pipefail

if [[ -z "${ALLURE_STOCK_CLI:-}" ]]; then
  if [[ -e /opt/node/bin/allure-stock ]]; then
    ALLURE_STOCK_CLI=/opt/node/bin/allure-stock
  elif [[ -e /usr/local/bin/allure-stock ]]; then
    ALLURE_STOCK_CLI=/usr/local/bin/allure-stock
  elif [[ -f /opt/node/lib/node_modules/allure/cli.js ]]; then
    ALLURE_STOCK_CLI=/opt/node/lib/node_modules/allure/cli.js
  elif [[ -f /usr/local/lib/node_modules/allure/cli.js ]]; then
    ALLURE_STOCK_CLI=/usr/local/lib/node_modules/allure/cli.js
  else
    ALLURE_STOCK_CLI=/opt/node/lib/node_modules/allure/cli.js
  fi
fi
STOCK_CLI="$ALLURE_STOCK_CLI"

tests_dir=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "--config" ]]; then
    tests_dir="$(dirname "${args[$i + 1]}")"
    break
  fi
done

if [[ -n "$tests_dir" && -f "${tests_dir}/package.json" ]]; then
  cd "$tests_dir"
  if [[ ! -d node_modules/@qa-guru/allure-report-kit-awesome ]]; then
    npm ci
  fi
  exec npx --no-install allure "$@"
fi

exec node "$STOCK_CLI" "$@"
