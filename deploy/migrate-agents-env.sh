#!/usr/bin/env bash
# One-time on server: extract agent secrets from docker-compose.yml into agents.env.
set -euo pipefail

CONFIG_DIR="${JENKINS_CONFIG_DIR:-/var/docker-compose-config}"
COMPOSE_FILE="${CONFIG_DIR}/docker-compose.yml"
OUT="${CONFIG_DIR}/agents.env"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Missing ${COMPOSE_FILE}" >&2
  exit 1
fi

extract_secret() {
  local service="$1"
  python - "$COMPOSE_FILE" "$service" <<'PY'
import re, sys
path, service = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
block = re.search(rf"^\s*{re.escape(service)}:\s*\n(.*?)(?=^\s{0,2}\S|\Z)", text, re.M | re.S)
if not block:
    raise SystemExit(f"service not found: {service}")
flat = block.group(1).replace("\n", " ")
m = re.search(r"http://jenkins:8080\s+(\S+)", flat)
if not m:
    raise SystemExit(f"secret not found in {service}")
print(m.group(1))
PY
}

umask 077
cat >"${OUT}" <<EOFENV
JENKINS_IMAGE=jenkins/jenkins:jdk21

JAVA_JDK21_AGENT_1_SECRET=$(extract_secret java-jdk21-jenkins-agent-1)
JAVA_JDK21_AGENT_2_SECRET=$(extract_secret java-jdk21-jenkins-agent-2)
JAVA_JDK21_AGENT_3_SECRET=$(extract_secret java-jdk21-jenkins-agent-3)
JAVA_JDK21_AGENT_4_SECRET=$(extract_secret java-jdk21-jenkins-agent-4)
JAVA_JDK21_AGENT_5_SECRET=$(extract_secret java-jdk21-jenkins-agent-5)

PYTHON_PYTHON314_AGENT_1_SECRET=$(extract_secret python-python314-jenkins-agent-1)
PYTHON_PYTHON314_AGENT_2_SECRET=$(extract_secret python-python314-jenkins-agent-2)
PYTHON_PYTHON314_AGENT_3_SECRET=$(extract_secret python-python314-jenkins-agent-3)
PYTHON_PYTHON314_AGENT_4_SECRET=$(extract_secret python-python314-jenkins-agent-4)
PYTHON_PYTHON314_AGENT_5_SECRET=$(extract_secret python-python314-jenkins-agent-5)
EOFENV

chown selenoid:docker "${OUT}" 2>/dev/null || true
echo "Wrote ${OUT} (chmod 600 recommended)"
