#!/usr/bin/env bash
# Deploy Jenkins stack to jenkins.qa.guru host.
# Run as deploy user (selenoid) — needs write access to JENKINS_CONFIG_DIR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${JENKINS_CONFIG_DIR:-/var/docker-compose-config}"
ENV_FILE="${JENKINS_AGENTS_ENV:-${CONFIG_DIR}/agents.env}"
COMPOSE="${DOCKER_COMPOSE:-docker compose}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  echo "Copy deploy/agents.env.example → ${ENV_FILE} and fill agent secrets." >&2
  exit 1
fi

echo "=== sync compose + agent Dockerfiles → ${CONFIG_DIR} ==="
install -d "${CONFIG_DIR}/jdk21-agent" "${CONFIG_DIR}/python3-agent" "${CONFIG_DIR}/bin"
install -m 644 "${SCRIPT_DIR}/docker-compose.yml" "${CONFIG_DIR}/docker-compose.yml"
install -m 644 "${SCRIPT_DIR}/jdk21-agent/Dockerfile" "${CONFIG_DIR}/jdk21-agent/Dockerfile"
install -m 644 "${SCRIPT_DIR}/python3-agent/Dockerfile" "${CONFIG_DIR}/python3-agent/Dockerfile"
install -m 755 "${SCRIPT_DIR}/sync-nginx.sh" "${CONFIG_DIR}/bin/sync-nginx.sh"

echo "=== pull Jenkins controller image ==="
# shellcheck disable=SC1090
set -a && source "${ENV_FILE}" && set +a
docker pull "${JENKINS_IMAGE:-jenkins/jenkins:jdk21}"

echo "=== build agent images ==="
cd "${CONFIG_DIR}"
${COMPOSE} --env-file "${ENV_FILE}" build

echo "=== up (preserve /var/jenkins_home) ==="
${COMPOSE} --env-file "${ENV_FILE}" up -d --remove-orphans

echo "=== status ==="
${COMPOSE} --env-file "${ENV_FILE}" ps

echo "Deploy complete."
