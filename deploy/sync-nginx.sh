#!/usr/bin/env bash
# Apply nginx-jenkins.conf on the server (requires sudo).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="${NGINX_CONF_SRC:-${SCRIPT_DIR}/nginx-jenkins.conf}"
SITE_NAME="${NGINX_SITE_NAME:-jenkins}"
SITE_PATH="/etc/nginx/sites-available/${SITE_NAME}"
TMP="/tmp/nginx-jenkins.generated"
SSL_SNIPPET="/tmp/nginx-jenkins.ssl-snippet"

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

: >"$SSL_SNIPPET"
if [[ -f "$SITE_PATH" ]]; then
  grep -E '^\s*ssl_certificate(_key)? ' "$SITE_PATH" | awk '!seen[$0]++' >>"$SSL_SNIPPET" || true
fi
if [[ ! -s "$SSL_SNIPPET" ]]; then
  for domain in jenkins.qa.guru jenkins.qa.guru-0001; do
    if [[ -f "/etc/letsencrypt/live/${domain}/fullchain.pem" ]]; then
      {
        echo "    ssl_certificate /etc/letsencrypt/live/${domain}/fullchain.pem;"
        echo "    ssl_certificate_key /etc/letsencrypt/live/${domain}/privkey.pem;"
      } >>"$SSL_SNIPPET"
      break
    fi
  done
fi
if [[ -s "$SSL_SNIPPET" ]]; then
  awk -v sslfile="$SSL_SNIPPET" '
    /# ssl_certificate \.\.\.;/ {
      while ((getline line < sslfile) > 0) print line
      close(sslfile)
      next
    }
    { print }
  ' "$TMP" >"${TMP}.patched"
  mv "${TMP}.patched" "$TMP"
else
  echo "WARN: no ssl_certificate lines found" >&2
fi

cp "$TMP" "$SITE_PATH"
ln -sf "$SITE_PATH" "/etc/nginx/sites-enabled/${SITE_NAME}"
nginx -t
systemctl reload nginx
echo "OK: nginx reloaded ($SITE_PATH)"
