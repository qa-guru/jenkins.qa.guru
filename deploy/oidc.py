#!/usr/bin/env python3
"""P4 — Jenkins oic-auth against https://auth.qa.guru.

Secrets stay in ~/.config (mode 600). Nothing here is printed.

  python3 deploy/oidc.py inventory
  python3 deploy/oidc.py seed-idp
  python3 deploy/oidc.py install-plugins
  python3 deploy/oidc.py configure
  python3 deploy/oidc.py login-check
  python3 deploy/oidc.py verify
  python3 deploy/oidc.py break-glass
  python3 deploy/oidc.py revert-local
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

JENKINS_URL = os.environ.get("JENKINS_URL", "https://jenkins.qa.guru").rstrip("/")
AUTH_URL = os.environ.get("AUTH_URL", "https://auth.qa.guru").rstrip("/")
REALM = os.environ.get("REALM", "qaguru")
CLIENT_ID = "jenkins"
BOX2 = os.environ.get("JENKINS_SSH", "box2-ci")
AUTH_SSH = os.environ.get("AUTH_SSH", "auth-qa-guru")
AUTH_ENV_FILE = Path(os.environ.get("AUTH_ENV", Path.home() / ".config/auth-qa-guru/keycloak.env"))
PILOT_ENV_FILE = Path(os.environ.get("PILOT_ENV", Path.home() / ".config/auth-qa-guru/pilot.env"))
HATCH_ENV_FILE = Path(os.environ.get("JENKINS_HATCH_ENV", Path.home() / ".config/jenkins/escape-hatch.env"))
INV_DIR = Path.home() / ".config/jenkins/p4-inventory"
PASSWORDS_FILE = INV_DIR / "kc-passwords.env"
QA_GURU_DIR = Path.home() / ".config/qa-guru"
WELL_KNOWN = f"{AUTH_URL}/realms/{REALM}/.well-known/openid-configuration"
ETALON_PATTERN = r"(autotests-ai-multistack-tests.*|41_MashaSelyanko_proect1)"
STUDENT_PATTERN = r"(?!autotests-ai-multistack-tests)(?!41_MashaSelyanko_proect1).*"

STAFF = {"svasenkov"}
BREAK_GLASS = {"admin"}
SERVICE = {"jenkins_service_acc", "cursor_demo_bot"}
NEVER_KEYCLOAK = BREAK_GLASS | SERVICE | {"SYSTEM", "agent"}
KC_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,128}$")

PILOT_PEOPLE = (
    {
        "env_user": "PILOT_STAFF_USERNAME",
        "env_pass": "PILOT_STAFF_PASSWORD",
        "env_email": "PILOT_STAFF_EMAIL",
        "username": "staff-pilot",
        "email": "staff-pilot@qa.guru",
        "firstName": "Staff",
        "lastName": "Pilot",
        "groups": ["/staff"],
        "expect_manage": True,
        "group": "/staff",
    },
    {
        "env_user": "PILOT_MENTOR_USERNAME",
        "env_pass": "PILOT_MENTOR_PASSWORD",
        "env_email": "PILOT_MENTOR_EMAIL",
        "username": "mentor-pilot",
        "email": "mentor-pilot@qa.guru",
        "firstName": "Mentor",
        "lastName": "Pilot",
        "groups": ["/mentors"],
        "expect_manage": False,
        "group": "/mentors",
    },
    {
        "env_user": "PILOT_STUDENT_USERNAME",
        "env_pass": "PILOT_STUDENT_PASSWORD",
        "env_email": "PILOT_STUDENT_EMAIL",
        "username": "student-pilot",
        "email": "student-pilot@qa.guru",
        "firstName": "Student",
        "lastName": "Pilot",
        "groups": ["/students"],
        "expect_manage": False,
        "group": "/students",
    },
)

GROOVY_INVENTORY = r"""
import groovy.json.JsonBuilder
import hudson.model.User
import hudson.model.Item
import hudson.security.HudsonPrivateSecurityRealm
import jenkins.model.Jenkins
import jenkins.security.ApiTokenProperty
import hudson.tasks.Mailer

def j = Jenkins.get()
def realm = j.getSecurityRealm()
def auth = j.getAuthorizationStrategy()
def users = []
User.getAll().each { u ->
  def mail = u.getProperty(Mailer.UserProperty)
  def tokens = u.getProperty(ApiTokenProperty)
  def tokenNames = []
  if (tokens != null) {
    try {
      tokenNames = tokens.getTokenListSortedByName().collect { it.name }
    } catch (ignored) {
      try { tokenNames = tokens.tokenStore.getTokenListSortedByName().collect { it.name } } catch (ignored2) {}
    }
  }
  def lastGranted = u.getProperty(jenkins.security.LastGrantedAuthoritiesProperty)
  users << [
    id: u.id,
    fullName: u.fullName,
    email: mail?.address,
    tokenCount: tokenNames.size(),
    tokenNames: tokenNames,
    lastGranted: lastGranted?.timestamp?.toString()
  ]
}
def jobs = j.getAllItems(Item).collect { it.fullName }
def pluginShort = j.pluginManager.plugins.collect {
  [shortName: it.shortName, version: it.version, enabled: it.isEnabled()]
}.sort { it.shortName }
def administer = []
try {
  def sids = auth.getGrantedPermissions()[Jenkins.ADMINISTER]
  if (sids != null) administer = sids.collect { it.toString() }
} catch (ignored) {}
def result = [
  jenkinsVersion: Jenkins.VERSION,
  rootUrl: j.rootUrl,
  realm: realm.getClass().getName(),
  allowsSignup: (realm instanceof HudsonPrivateSecurityRealm) ? realm.allowsSignup() : false,
  authorization: auth.getClass().getName(),
  administerSids: administer,
  userCount: users.size(),
  users: users.sort { it.id },
  jobCount: jobs.size(),
  jobs: jobs,
  pluginCount: pluginShort.size(),
  hasOic: pluginShort.any { it.shortName == "oic-auth" },
  hasRoleStrategy: pluginShort.any { it.shortName == "role-strategy" },
  oicVersion: pluginShort.find { it.shortName == "oic-auth" }?.version,
  roleStrategyVersion: pluginShort.find { it.shortName == "role-strategy" }?.version,
  rootURLFromRequest: realm.metaClass.respondsTo(realm, "isRootURLFromRequest") ? realm.isRootURLFromRequest() : null
]
println new JsonBuilder(result).toPrettyString()
"""


def ssl_ctx() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def load_kv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def upsert_kv(path: Path, updates: dict[str, str], header: str) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    env = load_kv(path)
    env.update(updates)
    lines = [header.rstrip(), ""]
    for key, value in env.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def ssh(host: str, script: str, *, check: bool = True) -> str:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host, "bash", "-s"],
        input=script.encode(),
        capture_output=True,
        check=False,
    )
    out = (proc.stdout or b"").decode("utf-8", "replace")
    if check and proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")[:800]
        raise SystemExit(f"ssh {host} failed ({proc.returncode}): {err or out[:400]}")
    return out


def jenkins_groovy(script: str) -> str:
    remote = r"""
set -euo pipefail
TOKEN=$(sudo cat /var/jenkins_home/secrets/admin-api-token.plain)
sudo tee /tmp/p4.groovy >/dev/null <<'GROOVY'
""" + script + r"""
GROOVY
curl -sf -u "admin:$TOKEN" --data-urlencode "script=$(sudo cat /tmp/p4.groovy)" \
  http://127.0.0.1:8082/scriptText
sudo rm -f /tmp/p4.groovy
"""
    return ssh(BOX2, remote)


def auth_env() -> dict[str, str]:
    env = load_kv(AUTH_ENV_FILE)
    if not env.get("KC_BOOTSTRAP_ADMIN_USERNAME") or not env.get("KC_CLIENT_SECRET_JENKINS"):
        raise SystemExit(f"missing Keycloak bootstrap or KC_CLIENT_SECRET_JENKINS in {AUTH_ENV_FILE}")
    return env


def keycloak_token(env: dict[str, str]) -> str:
    form = urllib.parse.urlencode(
        {
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": env["KC_BOOTSTRAP_ADMIN_USERNAME"],
            "password": env["KC_BOOTSTRAP_ADMIN_PASSWORD"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{AUTH_URL}/realms/master/protocol/openid-connect/token",
        data=form,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=ssl_ctx()) as resp:
        return json.loads(resp.read())["access_token"]


def kc(method: str, path: str, token: str, body: Any = None) -> Any:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{AUTH_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx()) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} -> {exc.code} {exc.read()[:300]!r}") from exc


def jobs_for(uid: str, jobs: list[str]) -> list[str]:
    uid_l = uid.lower()
    hits = []
    for job in jobs:
        jl = job.lower()
        if jl == uid_l or jl.startswith(uid_l + "-") or jl.startswith(uid_l + "_"):
            hits.append(job)
    return hits


def known_local_logins() -> set[str]:
    out: set[str] = set()
    if not QA_GURU_DIR.is_dir():
        return out
    for path in QA_GURU_DIR.glob("*-access.txt"):
        out.add(path.name.replace("-access.txt", ""))
    for path in QA_GURU_DIR.glob("*.password"):
        out.add(path.name.replace(".password", ""))
    return out - STAFF - BREAK_GLASS


def classify(user: dict[str, Any], jobs: list[str], known: set[str]) -> tuple[str, str]:
    uid = str(user["id"])
    hits = jobs_for(uid, jobs)
    if uid in BREAK_GLASS:
        return "break-glass", "local escapeHatch; never create in Keycloak; API tokens live here"
    if uid in STAFF:
        return "staff", "keep current username; Keycloak /staff"
    if uid in SERVICE:
        return "service", "machine token; Role Strategy USER assignment; not in Keycloak"
    if uid in {"SYSTEM"}:
        return "junk", "Jenkins internal SYSTEM"
    if re.match(r"^\d+\+", uid) or str(user.get("email") or "").endswith("@users.noreply.github.com"):
        return "junk", "github noreply / numeric+login"
    if uid.lower() in {"root", "superadmin"} or "sadflk" in uid.lower():
        return "junk", "probe-like name"
    app_tests = [j for j in hits if "app-tests" in j.lower()]
    if uid in known or app_tests or hits:
        return "live-student", "owns jobs or provisioned contour"
    if user.get("tokenCount"):
        return "live-student", "has API tokens — keep and seed /students"
    if user.get("lastGranted"):
        return "live-student", "logged in (lastGranted); self-registered, seed /students"
    return "junk", "never logged in, no tokens, no jobs"


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------


def cmd_inventory() -> int:
    INV_DIR.mkdir(mode=0o700, exist_ok=True)
    raw = jenkins_groovy(GROOVY_INVENTORY)
    data = json.loads(raw)
    known = known_local_logins()
    jobs = data.get("jobs") or []
    mapping = []
    counts: dict[str, int] = {}
    token_owners = []
    for user in data.get("users") or []:
        bucket, decision = classify(user, jobs, known)
        counts[bucket] = counts.get(bucket, 0) + 1
        hits = jobs_for(str(user["id"]), jobs)
        row = {
            "jenkins_username": user["id"],
            "handle": user["id"],
            "email": user.get("email"),
            "bucket": bucket,
            "decision": decision,
            "jobs": hits,
            "tokenCount": user.get("tokenCount") or 0,
            "tokenNames": user.get("tokenNames") or [],
            "seed_keycloak": bucket in {"staff", "live-student"} and KC_USERNAME.match(str(user["id"])) is not None,
        }
        mapping.append(row)
        if row["tokenCount"]:
            token_owners.append(
                {"id": user["id"], "tokenCount": row["tokenCount"], "tokenNames": row["tokenNames"], "bucket": bucket}
            )
    payload = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "jenkinsVersion": data.get("jenkinsVersion"),
        "realm": data.get("realm"),
        "allowsSignup": data.get("allowsSignup"),
        "authorization": data.get("authorization"),
        "administerSids": data.get("administerSids"),
        "user_count": data.get("userCount"),
        "job_count": data.get("jobCount"),
        "plugin_count": data.get("pluginCount"),
        "has_oic": data.get("hasOic"),
        "has_role_strategy": data.get("hasRoleStrategy"),
        "classification_counts": counts,
        "known_local_contours": sorted(known),
        "token_owners": token_owners,
        "token_plan": (
            "API tokens live on User objects. oic-auth allowTokenAccessWithoutOicSession=true. "
            "admin keeps USER assignment on Role Strategy admin. Other token owners get USER student role "
            "so TestOps/CI tokens survive without an OIDC session. Reissue only if verify shows 401. "
            "Never create admin in Keycloak."
        ),
        "cleanup_plan": (
            "Junk is marked, not deleted. Realm-swap locks them out (no Keycloak account) without dropping user_count. "
            "Physical deletion is a later conscious step, not this window."
        ),
        "users": data.get("users"),
        "jobs": jobs,
        "username_map": mapping,
    }
    dest_name = os.environ.get("P4_SNAPSHOT")
    if not dest_name:
        dest_name = "after.json" if (INV_DIR / "before.json").is_file() else "before.json"
    dest = INV_DIR / dest_name
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dest.chmod(0o600)
    (INV_DIR / "username-map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    (INV_DIR / "username-map.json").chmod(0o600)
    cfg = ssh(BOX2, "sudo cat /var/jenkins_home/config.xml")
    cfg_path = INV_DIR / f"config.xml.{dest_name.replace('.json', '')}"
    cfg_path.write_text(cfg, encoding="utf-8")
    cfg_path.chmod(0o600)
    print(
        json.dumps(
            {
                "ok": True,
                "user_count": data.get("userCount"),
                "job_count": data.get("jobCount"),
                "classification": counts,
                "token_owners": [t["id"] for t in token_owners],
                "seed_keycloak": sum(1 for m in mapping if m["seed_keycloak"]),
                "wrote": str(dest),
                "realm": data.get("realm"),
                "allowsSignup": data.get("allowsSignup"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Keycloak people
# ---------------------------------------------------------------------------


def ensure_pilot_env() -> dict[str, str]:
    env = load_kv(PILOT_ENV_FILE)
    updates = {
        "PILOT_STAFF_USERNAME": env.get("PILOT_STAFF_USERNAME") or "staff-pilot",
        "PILOT_STAFF_EMAIL": env.get("PILOT_STAFF_EMAIL") or "staff-pilot@qa.guru",
        "PILOT_STAFF_PASSWORD": env.get("PILOT_STAFF_PASSWORD") or secrets.token_urlsafe(18),
        "PILOT_MENTOR_USERNAME": env.get("PILOT_MENTOR_USERNAME") or "mentor-pilot",
        "PILOT_MENTOR_EMAIL": env.get("PILOT_MENTOR_EMAIL") or "mentor-pilot@qa.guru",
        "PILOT_MENTOR_PASSWORD": env.get("PILOT_MENTOR_PASSWORD") or secrets.token_urlsafe(18),
        "PILOT_STUDENT_USERNAME": env.get("PILOT_STUDENT_USERNAME") or "student-pilot",
        "PILOT_STUDENT_EMAIL": env.get("PILOT_STUDENT_EMAIL") or "student-pilot@qa.guru",
        "PILOT_STUDENT_PASSWORD": env.get("PILOT_STUDENT_PASSWORD") or secrets.token_urlsafe(18),
    }
    upsert_kv(PILOT_ENV_FILE, updates, "# P2b/P4 pilot people on prod Keycloak. Mode 600. Not git, not chat.")
    return load_kv(PILOT_ENV_FILE)


def ensure_hatch_env() -> dict[str, str]:
    env = load_kv(HATCH_ENV_FILE)
    updates = {
        "ESCAPE_HATCH_USERNAME": env.get("ESCAPE_HATCH_USERNAME") or "admin",
        "ESCAPE_HATCH_GROUP": env.get("ESCAPE_HATCH_GROUP") or "/staff",
        "ESCAPE_HATCH_SECRET": env.get("ESCAPE_HATCH_SECRET") or secrets.token_urlsafe(24),
    }
    upsert_kv(HATCH_ENV_FILE, updates, "# P4 oic-auth escapeHatch. Mode 600. Not git, not chat.")
    return load_kv(HATCH_ENV_FILE)


def _group_ids(token: str) -> dict[str, str]:
    groups = kc("GET", f"/admin/realms/{REALM}/groups", token) or []
    return {g["path"]: g["id"] for g in groups}


def upsert_kc_user(
    token: str,
    paths: dict[str, str],
    *,
    username: str,
    password: str,
    email: str | None,
    first_name: str,
    last_name: str,
    groups: list[str],
) -> str:
    existing = kc(
        "GET",
        f"/admin/realms/{REALM}/users?username={urllib.parse.quote(username)}&exact=true",
        token,
    ) or []
    payload: dict[str, Any] = {
        "username": username,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
        "emailVerified": True,
        "requiredActions": [],
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    if email and "@" in email and " " not in email:
        payload["email"] = email
    else:
        payload["email"] = f"{username}@noreply.jenkins.qa.guru"
    if existing:
        user_id = existing[0]["id"]
        kc("PUT", f"/admin/realms/{REALM}/users/{user_id}", token, payload)
        action = "updated"
    else:
        kc("POST", f"/admin/realms/{REALM}/users", token, payload)
        created = kc(
            "GET",
            f"/admin/realms/{REALM}/users?username={urllib.parse.quote(username)}&exact=true",
            token,
        )
        user_id = created[0]["id"]
        action = "created"
    kc(
        "PUT",
        f"/admin/realms/{REALM}/users/{user_id}/reset-password",
        token,
        {"type": "password", "value": password, "temporary": False},
    )
    for path in groups:
        gid = paths.get(path)
        if not gid:
            raise SystemExit(f"Keycloak group {path} missing — realm import broken")
        try:
            kc("PUT", f"/admin/realms/{REALM}/users/{user_id}/groups/{gid}", token, {})
        except RuntimeError as exc:
            if "409" not in str(exc):
                raise
    return action


def local_password_for(login: str) -> str | None:
    path = QA_GURU_DIR / f"{login}.password"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    stored = load_kv(PASSWORDS_FILE)
    return stored.get(login)


def cmd_seed_idp() -> int:
    if not (INV_DIR / "before.json").is_file():
        raise SystemExit("run inventory first")
    before = json.loads((INV_DIR / "before.json").read_text(encoding="utf-8"))
    mapping = before.get("username_map") or []
    pilot = ensure_pilot_env()
    token = keycloak_token(auth_env())
    paths = _group_ids(token)
    results = []
    stored = load_kv(PASSWORDS_FILE)
    for person in PILOT_PEOPLE:
        username = pilot.get(person["env_user"], person["username"])
        password = pilot[person["env_pass"]]
        email = pilot.get(person["env_email"], person["email"])
        action = upsert_kc_user(
            token,
            paths,
            username=username,
            password=password,
            email=email,
            first_name=person["firstName"],
            last_name=person["lastName"],
            groups=person["groups"],
        )
        results.append({"username": username, "action": action, "groups": person["groups"], "kind": "pilot"})
    seeded = {r["username"] for r in results}
    for row in mapping:
        username = str(row["jenkins_username"])
        if not row.get("seed_keycloak") or username in seeded:
            continue
        if not KC_USERNAME.match(username) or username in NEVER_KEYCLOAK:
            results.append({"username": username, "action": "skipped", "groups": [], "kind": "skipped"})
            continue
        password = local_password_for(username) or stored.get(username) or secrets.token_urlsafe(18)
        stored[username] = password
        email = row.get("email") if isinstance(row.get("email"), str) and "@" in str(row.get("email")) else None
        try:
            action = upsert_kc_user(
                token,
                paths,
                username=username,
                password=password,
                email=email,
                first_name=username[:80],
                last_name="student",
                groups=["/students"],
            )
        except RuntimeError as exc:
            if "401" in str(exc):
                token = keycloak_token(auth_env())
                paths = _group_ids(token)
                try:
                    action = upsert_kc_user(
                        token,
                        paths,
                        username=username,
                        password=password,
                        email=email,
                        first_name=username[:80],
                        last_name="student",
                        groups=["/students"],
                    )
                except RuntimeError as exc2:
                    results.append({"username": username, "action": f"error:{exc2}"[:180], "groups": [], "kind": "error"})
                    continue
            else:
                results.append({"username": username, "action": f"error:{exc}"[:180], "groups": [], "kind": "error"})
                continue
        results.append({"username": username, "action": action, "groups": ["/students"], "kind": "migrated"})
    if stored:
        upsert_kv(PASSWORDS_FILE, stored, "# P4 migrated Jenkins students → Keycloak. Mode 600. Not git, not chat.")
    print(
        json.dumps(
            {
                "ok": True,
                "pilot_env": str(PILOT_ENV_FILE),
                "migrated_passwords": str(PASSWORDS_FILE) if stored else None,
                "counts": {
                    "pilot": sum(1 for r in results if r["kind"] == "pilot"),
                    "migrated": sum(1 for r in results if r["kind"] == "migrated"),
                    "skipped": sum(1 for r in results if r["kind"] == "skipped"),
                    "error": sum(1 for r in results if r["kind"] == "error"),
                },
                "users": [{"username": r["username"], "action": r["action"], "groups": r["groups"], "kind": r["kind"]} for r in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------


def wait_jenkins(timeout: int = 180) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        last = ssh(
            BOX2,
            "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8082/login || true",
            check=False,
        ).strip()
        if last in {"200", "403"}:
            return
        time.sleep(3)
    raise SystemExit(f"Jenkins did not come back, last /login HTTP {last}")


def cmd_install_plugins() -> int:
    out = ssh(
        BOX2,
        r"""
set -euo pipefail
IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' jenkins)
echo "image=$IMAGE"
sudo docker stop jenkins
sudo docker run --rm --user root -v /var/jenkins_home:/var/jenkins_home "$IMAGE" \
  jenkins-plugin-cli --plugin-download-directory /var/jenkins_home/plugins \
  --plugins oic-auth role-strategy
sudo docker start jenkins
echo "restarted"
""",
    )
    wait_jenkins()
    raw = jenkins_groovy(GROOVY_INVENTORY)
    data = json.loads(raw)
    print(
        json.dumps(
            {
                "ok": True,
                "install": out.strip().splitlines()[-3:],
                "has_oic": data.get("hasOic"),
                "has_role_strategy": data.get("hasRoleStrategy"),
                "oic_version": data.get("oicVersion"),
                "role_strategy_version": data.get("roleStrategyVersion"),
            },
            indent=2,
        )
    )
    if not data.get("hasOic") or not data.get("hasRoleStrategy"):
        raise SystemExit("plugins missing after restart")
    return 0


# ---------------------------------------------------------------------------
# configure OIDC + Role Strategy
# ---------------------------------------------------------------------------


def groovy_configure(token_sids: list[str]) -> str:
    token_literal = ", ".join(f'"{sid}"' for sid in token_sids)
    return f"""
import java.util.regex.Pattern
import hudson.model.Item
import hudson.model.View
import hudson.util.Secret
import jenkins.model.Jenkins
import hudson.security.Permission
import org.jenkinsci.plugins.oic.OicSecurityRealm
import org.jenkinsci.plugins.oic.OicServerWellKnownConfiguration
import org.jenkinsci.plugins.oic.properties.EscapeHatch
import org.jenkinsci.plugins.oic.properties.Pkce
import com.michelin.cio.hudson.plugins.rolestrategy.AuthorizationType
import com.michelin.cio.hudson.plugins.rolestrategy.PermissionEntry
import com.michelin.cio.hudson.plugins.rolestrategy.RoleBasedAuthorizationStrategy
import com.michelin.cio.hudson.plugins.rolestrategy.Role
import com.synopsys.arc.jenkins.plugins.rolestrategy.RoleType

def j = Jenkins.get()
def clientSecret = new File("/var/jenkins_home/.p4_oidc_client_secret").text.trim()
def hatchSecret = new File("/var/jenkins_home/.p4_escape_hatch_secret").text.trim()

def wellKnown = new OicServerWellKnownConfiguration("{WELL_KNOWN}")
wellKnown.setScopesOverride("openid profile email")

def realm = new OicSecurityRealm("jenkins", Secret.fromString(clientSecret), wellKnown, false, null, null)
realm.createProxyAwareResourceRetriver()
realm.setUserNameField("preferred_username")
realm.setFullNameFieldName("name")
realm.setEmailFieldName("email")
realm.setGroupsFieldName("groups")
realm.setLogoutFromOpenidProvider(true)
realm.setPostLogoutRedirectUrl("https://jenkins.qa.guru/OicLogout")
realm.setAllowTokenAccessWithoutOicSession(true)
// false: token refresh runs in a servlet filter before Stapler binds the request.
// getRootUrlFromRequest() there throws and 500s every asset (oic-auth #506).
realm.setRootURLFromRequest(false)
realm.setProperties([
  new EscapeHatch("admin", "/staff", Secret.fromString(hatchSecret)),
  new Pkce()
])

def rbas = new RoleBasedAuthorizationStrategy()

Set adminPerms = new HashSet()
adminPerms.add(Jenkins.ADMINISTER)
Role adminRole = new Role("admin", Pattern.compile(".*"), adminPerms, "Keycloak /staff + escapeHatch admin")

Set mentorPerms = new HashSet()
mentorPerms.add(Jenkins.READ)
mentorPerms.add(Item.READ)
mentorPerms.add(Item.DISCOVER)
mentorPerms.add(Item.WORKSPACE)
mentorPerms.add(Item.BUILD)
mentorPerms.add(View.READ)
Role mentorRole = new Role("mentor", Pattern.compile(".*"), mentorPerms, "Keycloak /mentors")

Set studentGlobal = new HashSet()
studentGlobal.add(Jenkins.READ)
studentGlobal.add(View.READ)
studentGlobal.add(Item.CREATE)
Role studentGlobalRole = new Role("student", Pattern.compile(".*"), studentGlobal, "Keycloak /students overall")

Set anonPerms = new HashSet()
anonPerms.add(Jenkins.READ)
anonPerms.add(View.READ)
Role anonRole = new Role("anonymous", Pattern.compile(".*"), anonPerms, "public Overall/Read")

def globalMap = rbas.getRoleMap(RoleType.Global)
globalMap.addRole(adminRole)
globalMap.addRole(mentorRole)
globalMap.addRole(studentGlobalRole)
globalMap.addRole(anonRole)
globalMap.assignRole(adminRole, new PermissionEntry(AuthorizationType.USER, "admin"))
globalMap.assignRole(adminRole, new PermissionEntry(AuthorizationType.GROUP, "/staff"))
globalMap.assignRole(mentorRole, new PermissionEntry(AuthorizationType.GROUP, "/mentors"))
globalMap.assignRole(studentGlobalRole, new PermissionEntry(AuthorizationType.GROUP, "/students"))
globalMap.assignRole(anonRole, new PermissionEntry(AuthorizationType.USER, "anonymous"))

Set etalonPerms = new HashSet()
etalonPerms.add(Item.READ)
etalonPerms.add(Item.DISCOVER)
etalonPerms.add(Item.WORKSPACE)
if (Item.EXTENDED_READ.getEnabled()) {{
  etalonPerms.add(Item.EXTENDED_READ)
}}
Role etalonRole = new Role("etalon", Pattern.compile("{ETALON_PATTERN}"), etalonPerms, "demo jobs, public read")

Set studentWork = new HashSet()
studentWork.add(Item.READ)
studentWork.add(Item.DISCOVER)
studentWork.add(Item.BUILD)
studentWork.add(Item.CANCEL)
studentWork.add(Item.CONFIGURE)
studentWork.add(Item.CREATE)
studentWork.add(Item.DELETE)
studentWork.add(Item.WORKSPACE)
Role studentWorkRole = new Role("student-work", Pattern.compile("{STUDENT_PATTERN}"), studentWork, "students: not etalon")

def itemMap = rbas.getRoleMap(RoleType.Project)
itemMap.addRole(etalonRole)
itemMap.addRole(studentWorkRole)
itemMap.assignRole(etalonRole, new PermissionEntry(AuthorizationType.USER, "anonymous"))
itemMap.assignRole(etalonRole, new PermissionEntry(AuthorizationType.GROUP, "/students"))
itemMap.assignRole(etalonRole, new PermissionEntry(AuthorizationType.GROUP, "/mentors"))
itemMap.assignRole(studentWorkRole, new PermissionEntry(AuthorizationType.GROUP, "/students"))

[{token_literal}].each {{ sid ->
  if (sid && sid != "admin") {{
    globalMap.assignRole(studentGlobalRole, new PermissionEntry(AuthorizationType.USER, sid))
    itemMap.assignRole(studentWorkRole, new PermissionEntry(AuthorizationType.USER, sid))
  }}
}}

try {{
  def nsClass = Class.forName("org.jenkinsci.plugins.rolestrategy.RoleBasedProjectNamingStrategy")
  j.setProjectNamingStrategy(nsClass.getDeclaredConstructor().newInstance())
  println "namingStrategy=role-based"
}} catch (Throwable t) {{
  println "namingStrategy=unchanged " + t.getClass().getSimpleName()
}}

j.setAuthorizationStrategy(rbas)
j.setSecurityRealm(realm)
j.save()
new File("/var/jenkins_home/.p4_oidc_client_secret").delete()
new File("/var/jenkins_home/.p4_escape_hatch_secret").delete()
println "realm=" + j.getSecurityRealm().getClass().getName()
println "auth=" + j.getAuthorizationStrategy().getClass().getName()
println "signupClosed=true"
"""


def cmd_configure() -> int:
    if not (INV_DIR / "before.json").is_file():
        raise SystemExit("run inventory first")
    env = auth_env()
    hatch = ensure_hatch_env()
    before = json.loads((INV_DIR / "before.json").read_text(encoding="utf-8"))
    token_sids = [t["id"] for t in before.get("token_owners") or [] if t.get("id")]
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ssh(
        BOX2,
        f"""
set -euo pipefail
sudo mkdir -p /var/jenkins_home/.p4-oidc-backup-{ts}
sudo cp -a /var/jenkins_home/config.xml /var/jenkins_home/.p4-oidc-backup-{ts}/config.xml
echo backup=/var/jenkins_home/.p4-oidc-backup-{ts}
""",
    )
    # secrets via stdin so they never sit in the Groovy source
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", BOX2, "sudo tee /var/jenkins_home/.p4_oidc_client_secret >/dev/null && sudo chmod 600 /var/jenkins_home/.p4_oidc_client_secret"],
        input=(env["KC_CLIENT_SECRET_JENKINS"] + "\n").encode(),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", BOX2, "sudo tee /var/jenkins_home/.p4_escape_hatch_secret >/dev/null && sudo chmod 600 /var/jenkins_home/.p4_escape_hatch_secret"],
        input=(hatch["ESCAPE_HATCH_SECRET"] + "\n").encode(),
        check=True,
        capture_output=True,
    )
    out = jenkins_groovy(groovy_configure(token_sids))
    print(out.strip())
    if "org.jenkinsci.plugins.oic.OicSecurityRealm" not in out:
        raise SystemExit("configure did not switch security realm")
    if "RoleBasedAuthorizationStrategy" not in out:
        raise SystemExit("configure did not switch Role Strategy")
    return 0


GROOVY_REVERT_LOCAL = r"""
import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.ProjectMatrixAuthorizationStrategy
import hudson.model.Item
import hudson.model.View

def j = Jenkins.get()
def current = j.getSecurityRealm().getClass().getName()
if (current.contains("HudsonPrivateSecurityRealm")) {
  println "already=HudsonPrivate"
  println "realm=" + current
  println "auth=" + j.getAuthorizationStrategy().getClass().getName()
  return
}

def realm = new HudsonPrivateSecurityRealm(false, true, null)
def strategy = new ProjectMatrixAuthorizationStrategy()
strategy.add(Jenkins.ADMINISTER, "admin")
strategy.add(Jenkins.ADMINISTER, "svasenkov")
strategy.add(Jenkins.READ, "anonymous")
strategy.add(Jenkins.READ, "authenticated")
strategy.add(Item.BUILD, "authenticated")
strategy.add(Item.CANCEL, "authenticated")
strategy.add(Item.CONFIGURE, "authenticated")
strategy.add(Item.CREATE, "authenticated")
strategy.add(Item.DELETE, "authenticated")
strategy.add(Item.DISCOVER, "authenticated")
strategy.add(Item.READ, "authenticated")
strategy.add(Item.WORKSPACE, "authenticated")
strategy.add(View.READ, "authenticated")

j.setAuthorizationStrategy(strategy)
j.setSecurityRealm(realm)
j.save()
println "realm=" + j.getSecurityRealm().getClass().getName()
println "auth=" + j.getAuthorizationStrategy().getClass().getName()
println "signupClosed=" + (!j.getSecurityRealm().allowsSignup())
"""


def cmd_revert_local() -> int:
    """HudsonPrivate + ProjectMatrix. Signup stays closed. OIDC/Keycloak untouched."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    offbox = Path.home() / ".config/jenkins" / f"p4-rollback-{ts}"
    offbox.mkdir(mode=0o700, parents=True, exist_ok=True)
    ssh(
        BOX2,
        f"""
set -euo pipefail
sudo mkdir -p /var/jenkins_home/.p4-rollback-{ts}
sudo cp -a /var/jenkins_home/config.xml /var/jenkins_home/.p4-rollback-{ts}/config.xml
echo backup=/var/jenkins_home/.p4-rollback-{ts}
""",
    )
    subprocess.run(
        [
            "scp",
            "-o",
            "BatchMode=yes",
            f"{BOX2}:/var/jenkins_home/.p4-rollback-{ts}/config.xml",
            str(offbox / "config.xml"),
        ],
        check=True,
        capture_output=True,
    )
    (offbox / "config.xml").chmod(0o600)
    out = jenkins_groovy(GROOVY_REVERT_LOCAL)
    print(out.strip())
    print(f"offbox={offbox}")
    if "hudson.security.HudsonPrivateSecurityRealm" not in out:
        raise SystemExit("revert-local did not switch security realm")
    if "ProjectMatrixAuthorizationStrategy" not in out and "already=HudsonPrivate" not in out:
        raise SystemExit("revert-local did not switch authorization strategy")
    return 0


# ---------------------------------------------------------------------------
# HTTP login helpers
# ---------------------------------------------------------------------------


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._current = {
                "action": ad.get("action", ""),
                "method": ad.get("method", "get").lower(),
                "id": ad.get("id", ""),
                "inputs": {},
            }
            self.forms.append(self._current)
        elif tag in {"input", "button"} and self._current is not None:
            name = ad.get("name")
            if name:
                self._current["inputs"][name] = ad.get("value", "")


def parse_forms(page: str) -> list[dict[str, Any]]:
    parser = FormParser()
    parser.feed(page)
    return parser.forms


def _join(base: str, action: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(action))


def http_code(url: str) -> int:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx()) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def oidc_login(username: str, password: str) -> dict[str, Any]:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx()),
        urllib.request.HTTPCookieProcessor(jar),
    )
    opener.addheaders = [("User-Agent", "qa-guru-p4-oidc/1.0")]

    def fetch(url: str, data: bytes | None = None) -> tuple[str, str, int]:
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        try:
            with opener.open(req, timeout=45) as resp:
                return resp.geturl(), resp.read().decode("utf-8", "replace"), resp.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            loc = exc.headers.get("Location")
            if exc.code in {301, 302, 303, 307, 308} and loc:
                return fetch(_join(url, loc), None)
            return url, body, exc.code

    url, page, status = fetch(f"{JENKINS_URL}/securityRealm/commenceLogin?from=%2FwhoAmI%2F")
    for _ in range(8):
        forms = parse_forms(page)
        login = next((f for f in forms if f.get("id") == "kc-form-login" or "username" in f["inputs"]), None)
        hatch = next((f for f in forms if "j_username" in f["inputs"]), None)
        if login and "username" in login["inputs"]:
            action = _join(url, login["action"])
            payload = dict(login["inputs"])
            payload["username"] = username
            payload["password"] = password
            payload.setdefault("credentialId", "")
            url, page, status = fetch(action, urllib.parse.urlencode(payload).encode())
            continue
        if hatch and status == 200 and "commenceLogin" not in url and "openid-connect" not in url:
            break
        if status in {200, 403} and "whoAmI" in url:
            break
        break

    session = next((c.value for c in jar if c.name.upper() == "JSESSIONID" or c.name == "JSESSIONID"), None)
    cookie = "; ".join(f"{c.name}={c.value}" for c in jar)
    req = urllib.request.Request(f"{JENKINS_URL}/whoAmI/api/json", headers={"Cookie": cookie})
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx()) as resp:
            who = json.loads(resp.read())
            who_status = resp.status
    except urllib.error.HTTPError as exc:
        who = json.loads(exc.read().decode("utf-8", "replace") or "{}")
        who_status = exc.code
    manage_code = 0
    try:
        req = urllib.request.Request(f"{JENKINS_URL}/manage", headers={"Cookie": cookie})
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx()) as resp:
            manage_code = resp.status
    except urllib.error.HTTPError as exc:
        manage_code = exc.code
    return {
        "username": username,
        "whoAmI": who,
        "who_status": who_status,
        "manage": manage_code,
        "authorities": who.get("authorities") if isinstance(who, dict) else None,
        "name": (who.get("name") or who.get("id")) if isinstance(who, dict) else None,
        "session": bool(session),
        "last_url": url,
        "last_status": status,
    }


def escape_hatch_login(username: str, password: str) -> dict[str, Any]:
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx()),
        urllib.request.HTTPCookieProcessor(jar),
    )
    opener.addheaders = [("User-Agent", "qa-guru-p4-oidc/1.0")]

    def fetch(url: str, data: bytes | None = None) -> tuple[str, str, int]:
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        try:
            with opener.open(req, timeout=30) as resp:
                return resp.geturl(), resp.read().decode("utf-8", "replace"), resp.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            loc = exc.headers.get("Location")
            if exc.code in {301, 302, 303, 307, 308} and loc:
                return fetch(_join(url, loc), None)
            return url, body, exc.code

    url, page, status = fetch(f"{JENKINS_URL}/login")
    forms = parse_forms(page)
    hatch = next((f for f in forms if "j_username" in f["inputs"] or "escapeHatch" in f.get("action", "")), None)
    if not hatch:
        return {"username": username, "whoAmI": {}, "manage": 0, "name": None, "error": "no escape hatch form", "login_status": status}
    payload = dict(hatch["inputs"])
    payload["j_username"] = username
    payload["j_password"] = password
    payload["from"] = payload.get("from") or "/whoAmI/"
    payload["Submit"] = "Sign in"
    action = _join(url, hatch["action"] or "securityRealm/escapeHatch")
    url, page, status = fetch(action, urllib.parse.urlencode(payload).encode())
    cookie = "; ".join(f"{c.name}={c.value}" for c in jar)
    who: Any = {}
    try:
        req = urllib.request.Request(f"{JENKINS_URL}/whoAmI/api/json", headers={"Cookie": cookie})
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx()) as resp:
            who = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        who = {"error": exc.code}
    manage = 0
    try:
        req = urllib.request.Request(f"{JENKINS_URL}/manage", headers={"Cookie": cookie})
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx()) as resp:
            manage = resp.status
    except urllib.error.HTTPError as exc:
        manage = exc.code
    return {
        "username": username,
        "whoAmI": who,
        "manage": manage,
        "name": (who.get("name") or who.get("id")) if isinstance(who, dict) else None,
        "authorities": who.get("authorities") if isinstance(who, dict) else None,
        "post_status": status,
        "url": url,
    }


def admin_token_ok() -> bool:
    out = ssh(
        BOX2,
        r"""
set -euo pipefail
TOKEN=$(sudo cat /var/jenkins_home/secrets/admin-api-token.plain)
curl -s -o /dev/null -w '%{http_code}' -u "admin:$TOKEN" http://127.0.0.1:8082/whoAmI/api/json
""",
        check=False,
    ).strip()
    return out == "200"


def cmd_login_check() -> int:
    pilot = load_kv(PILOT_ENV_FILE)
    if not pilot.get("PILOT_STAFF_PASSWORD"):
        raise SystemExit(f"missing {PILOT_ENV_FILE} — run seed-idp first")
    results = []
    for person in PILOT_PEOPLE:
        username = pilot.get(person["env_user"], person["username"])
        password = pilot[person["env_pass"]]
        me = oidc_login(username, password)
        authorities = {str(a) for a in (me.get("authorities") or [])}
        expect_group = person["group"]
        ok = (
            me.get("name") == username
            and expect_group in authorities
            and (me.get("manage") == 200) is person["expect_manage"]
        )
        results.append(
            {
                "username": username,
                "ok": ok,
                "expect_group": expect_group,
                "expect_manage": person["expect_manage"],
                "got": {
                    "name": me.get("name"),
                    "authorities": sorted(authorities),
                    "manage": me.get("manage"),
                },
            }
        )
        if not ok:
            print(json.dumps({"ok": False, "results": results, "raw": me}, ensure_ascii=False, indent=2))
            return 1
    groups = [r["got"]["authorities"] for r in results]
    different = len({tuple(g) for g in groups}) == 3
    manage_codes = [r["got"]["manage"] for r in results]
    print(
        json.dumps(
            {
                "ok": True,
                "staff_mentors_students_differ": different,
                "manage_codes": manage_codes,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if different and manage_codes[0] == 200 and manage_codes[1] != 200 and manage_codes[2] != 200 else 1


def cmd_verify() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    raw = jenkins_groovy(GROOVY_INVENTORY)
    data = json.loads(raw)
    check("oic-auth realm", "OicSecurityRealm" in str(data.get("realm")), str(data.get("realm")))
    check("root URL from request off", data.get("rootURLFromRequest") is False, str(data.get("rootURLFromRequest")))
    check("Role Strategy", "RoleBasedAuthorizationStrategy" in str(data.get("authorization")), str(data.get("authorization")))
    check("signup closed", data.get("allowsSignup") is False, str(data.get("allowsSignup")))
    signup = http_code(f"{JENKINS_URL}/signup")
    check("https /signup is 404", signup == 404, str(signup))
    login = http_code(f"{JENKINS_URL}/login")
    check("https /login reachable", login in {200, 403}, str(login))
    check("admin API token", admin_token_ok())
    before = json.loads((INV_DIR / "before.json").read_text(encoding="utf-8")) if (INV_DIR / "before.json").is_file() else {}
    before_n = int(before.get("user_count") or 0)
    now = int(data.get("userCount") or 0)
    check("user count did not drop", now >= before_n, f"{before_n} -> {now}")
    script = http_code(f"{JENKINS_URL}/computer/(built-in)/script")
    check("anon script console 403", script == 403, str(script))
    width = max(len(n) for n, _, _ in checks)
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'FAIL'}  {name.ljust(width)}  {detail}".rstrip())
    failed = [n for n, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


def _docker_keycloak(action: str) -> subprocess.CompletedProcess[str]:
    container = os.environ.get("KEYCLOAK_CONTAINER", "auth-qa-guru-keycloak-1")
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", AUTH_SSH, f"sudo docker {action} {container}"],
        check=False,
        capture_output=True,
        text=True,
    )


def cmd_break_glass() -> int:
    hatch = ensure_hatch_env()
    if not admin_token_ok():
        raise SystemExit("admin API token dead before Keycloak stop")
    print("ok    admin token before stop")
    stop = _docker_keycloak("stop")
    if stop.returncode != 0:
        raise SystemExit(f"failed to stop Keycloak: {stop.stderr or stop.stdout}")
    result = 1
    restarted = False
    ready = False
    try:
        time.sleep(2)
        oidc_status = http_code(f"{JENKINS_URL}/securityRealm/commenceLogin")
        token_ok = admin_token_ok()
        hatch_login = escape_hatch_login(hatch["ESCAPE_HATCH_USERNAME"], hatch["ESCAPE_HATCH_SECRET"])
        hatch_ok = hatch_login.get("name") == "admin" and hatch_login.get("manage") == 200
        print(
            json.dumps(
                {
                    "oidc_commence": oidc_status,
                    "admin_token": token_ok,
                    "escape_hatch": {"name": hatch_login.get("name"), "manage": hatch_login.get("manage"), "authorities": hatch_login.get("authorities")},
                },
                indent=2,
            )
        )
        if token_ok and hatch_ok:
            print("ok    escapeHatch + admin token while Keycloak is down")
            result = 0
        else:
            print("FAIL  break-glass did not work", file=sys.stderr)
    finally:
        start = _docker_keycloak("start")
        restarted = start.returncode == 0
        if restarted:
            for _ in range(40):
                if http_code(WELL_KNOWN) == 200:
                    print("ok    Keycloak back")
                    ready = True
                    break
                time.sleep(3)
        if not restarted:
            print(
                "FAIL  Keycloak did not start back — ssh auth-qa-guru 'sudo docker start auth-qa-guru-keycloak-1'",
                file=sys.stderr,
            )
        elif not ready:
            print("FAIL  Keycloak did not become ready", file=sys.stderr)
    if not restarted or not ready:
        return 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "command",
        choices=(
            "inventory",
            "seed-idp",
            "install-plugins",
            "configure",
            "login-check",
            "verify",
            "break-glass",
            "revert-local",
        ),
    )
    args = parser.parse_args()
    dispatch = {
        "inventory": cmd_inventory,
        "seed-idp": cmd_seed_idp,
        "install-plugins": cmd_install_plugins,
        "configure": cmd_configure,
        "login-check": cmd_login_check,
        "verify": cmd_verify,
        "break-glass": cmd_break_glass,
        "revert-local": cmd_revert_local,
    }
    return dispatch[args.command]()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} {exc.url} {exc.read()[:300]!r}", file=sys.stderr)
        raise
