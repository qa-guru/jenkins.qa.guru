#!/usr/bin/env bash
# Apply nginx-jenkins.conf on the server (requires sudo).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="${NGINX_CONF_SRC:-${SCRIPT_DIR}/nginx-jenkins.conf}"
SITE_NAME="${NGINX_SITE_NAME:-jenkins}"
SITE_PATH="/etc/nginx/sites-available/${SITE_NAME}"
TMP="/tmp/nginx-jenkins.generated"

if [[ ! -f "$CONF_SRC" ]]; then
  echo "Missing $CONF_SRC" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true 2>/dev/null; then
    exec sudo env NGINX_CONF_SRC="$CONF_SRC" NGINX_SITE_NAME="$SITE_NAME" "$0" "$@"
  fi
  echo "Run as root or with passwordless sudo" >&2
  exit 1
fi

cp "$CONF_SRC" "$TMP"

# Fill leftover placeholders with the Let's Encrypt cert for the nearest
# server_name. Never copy every ssl_certificate from the live site into every
# block: stacking RSA (jenkins.qa.guru) + ECDSA (jenkins.autotests.cloud) makes
# clients pick the RSA cert, which has no autotests.cloud SAN.
if grep -q '# ssl_certificate \.\.\.;' "$TMP"; then
  awk '
    $1 == "server_name" {
      name = $2
      sub(/;/, "", name)
    }
    /# ssl_certificate \.\.\.;/ {
      cert = "/etc/letsencrypt/live/" name "/fullchain.pem"
      key  = "/etc/letsencrypt/live/" name "/privkey.pem"
      if (name != "" && !system("test -f " cert)) {
        print "    ssl_certificate " cert ";"
        print "    ssl_certificate_key " key ";"
      } else {
        print "WARN: no cert for server_name " name > "/dev/stderr"
      }
      next
    }
    /# ssl_certificate_key \.\.\.;/ { next }
    { print }
  ' "$TMP" >"${TMP}.patched"
  mv "${TMP}.patched" "$TMP"
fi

missing=0
while read -r cert; do
  [[ -z "$cert" ]] && continue
  if [[ ! -f "$cert" ]]; then
    echo "Missing certificate file: $cert" >&2
    missing=1
  fi
done < <(awk '$1 == "ssl_certificate" { gsub(/;/, "", $2); print $2 }' "$TMP")
if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

cp "$TMP" "$SITE_PATH"
ln -sf "$SITE_PATH" "/etc/nginx/sites-enabled/${SITE_NAME}"
nginx -t
systemctl reload nginx
echo "OK: nginx reloaded ($SITE_PATH)"
