#!/usr/bin/env bash
# Apply tracked freestyle job configs under deploy/jobs/ to /var/jenkins_home.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JENKINS_HOME="${JENKINS_HOME:-/var/jenkins_home}"
JOBS_SRC="${ROOT}/jobs"

if [[ ! -d "$JOBS_SRC" ]]; then
  echo "No jobs directory: $JOBS_SRC" >&2
  exit 1
fi

shopt -s nullglob
mapfile -t configs < <(find "$JOBS_SRC" -name config.xml | sort)
if ((${#configs[@]} == 0)); then
  echo "No config.xml files under $JOBS_SRC" >&2
  exit 1
fi

for src in "${configs[@]}"; do
  rel="${src#"$JOBS_SRC/"}"
  job_path="${rel%/config.xml}"
  dst="${JENKINS_HOME}/jobs/${job_path}/config.xml"
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    cp "$dst" "${dst}.bak-$(date +%Y%m%d%H%M%S)"
  fi
  cp "$src" "$dst"
  test -f "$dst"
  echo "synced ${job_path} -> ${dst}"
done

# Reload job definitions without full Jenkins restart (best-effort).
if curl -sf -o /dev/null -X POST "http://127.0.0.1:8082/reload"; then
  echo "Jenkins config reloaded"
else
  echo "WARN: Jenkins reload skipped (config.xml is on disk; UI reload optional)" >&2
fi
