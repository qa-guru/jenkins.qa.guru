#!/usr/bin/env bash
# Install tracked freestyle job config.xml into jenkins_home (run on prod host).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JENKINS_HOME="${JENKINS_HOME:-/var/jenkins_home}"
JOBS_SRC="${ROOT}/jobs"
CONFIG_DIR="${JENKINS_CONFIG_DIR:-/var/docker-compose-config}"

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
  echo "installed ${job_path} -> ${dst}"
done

reload_jenkins() {
  if curl -sf -X POST "http://127.0.0.1:8082/reload"; then
    echo "Jenkins reload OK"
    return 0
  fi
  if [[ -d "$CONFIG_DIR" ]] && command -v docker >/dev/null; then
    (cd "$CONFIG_DIR" && docker compose --env-file agents.env restart jenkins)
    for i in $(seq 1 30); do
      if curl -sf http://127.0.0.1:8082/login -o /dev/null; then
        echo "Jenkins ready after restart (attempt $i)"
        return 0
      fi
      sleep 5
    done
  fi
  echo "WARN: Jenkins reload/restart did not confirm ready" >&2
  return 1
}

reload_jenkins || true
