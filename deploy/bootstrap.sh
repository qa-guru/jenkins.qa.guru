#!/usr/bin/env bash
# One-time bootstrap for jenkins.qa.guru deploy via GitHub Actions (user selenoid).
# Run on the server as root.
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-selenoid}"
CONFIG_DIR="${JENKINS_CONFIG_DIR:-/var/docker-compose-config}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo ./deploy/bootstrap.sh" >&2
  exit 1
fi

if ! id "$DEPLOY_USER" &>/dev/null; then
  echo "User ${DEPLOY_USER} does not exist" >&2
  exit 1
fi

echo "=== config dir ${CONFIG_DIR} ==="
install -d -o "${DEPLOY_USER}" -g docker -m 775 "${CONFIG_DIR}/bin"
install -d -o "${DEPLOY_USER}" -g docker -m 775 "${CONFIG_DIR}/java-jdk21-agent" "${CONFIG_DIR}/python-python314-agent"

echo "=== ownership for deploy user ${DEPLOY_USER} ==="
chown -R "${DEPLOY_USER}:docker" "${CONFIG_DIR}"
chmod 775 "${CONFIG_DIR}" "${CONFIG_DIR}/bin" "${CONFIG_DIR}/java-jdk21-agent" "${CONFIG_DIR}/python-python314-agent" 2>/dev/null || true

if [[ ! -f "${CONFIG_DIR}/agents.env" ]]; then
  echo "WARN: create ${CONFIG_DIR}/agents.env from deploy/agents.env.example before first deploy" >&2
fi

echo "=== passwordless sudo for nginx sync ==="
SUDOERS="/etc/sudoers.d/${DEPLOY_USER}-jenkins-nginx"
cat >"$SUDOERS" <<EOF
${DEPLOY_USER} ALL=(ALL) NOPASSWD: SETENV: ${CONFIG_DIR}/bin/sync-nginx.sh
${DEPLOY_USER} ALL=(ALL) NOPASSWD: SETENV: /tmp/sync-jenkins-nginx.sh
EOF
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"

echo "Bootstrap complete."
echo "  deploy user: ${DEPLOY_USER}"
echo "  config:      ${CONFIG_DIR}"
echo "Next:"
echo "  1. ${CONFIG_DIR}/agents.env  (secrets, chmod 600)"
echo "  2. ./deploy/deploy.sh        (as ${DEPLOY_USER})"
