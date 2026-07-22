#!/usr/bin/env bash
# Install tracked freestyle job config.xml into jenkins_home (run on prod host).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JENKINS_HOME="${JENKINS_HOME:-/var/jenkins_home}"
JOBS_SRC="${ROOT}/jobs"

mapfile -t configs < <(find "$JOBS_SRC" -name config.xml | sort)
if ((${#configs[@]} == 0)); then
  echo "No config.xml under $JOBS_SRC" >&2
  exit 1
fi

for src in "${configs[@]}"; do
  rel="${src#"$JOBS_SRC/"}"
  job_path="${rel%/config.xml}"
  dst="${JENKINS_HOME}/jobs/${job_path}/config.xml"
  sudo mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    sudo cp "$dst" "${dst}.bak-$(date +%Y%m%d%H%M%S)"
  fi
  sudo install -m 644 "$src" "$dst"
  echo "installed ${job_path}"
done

curl -sf -X POST http://127.0.0.1:8082/reload || echo "WARN: reload skipped" >&2
