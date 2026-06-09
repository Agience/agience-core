#!/bin/sh
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

BACKEND_URI="${VITE_BACKEND_URI:-http://localhost:8081}"
CLIENT_ID="${VITE_CLIENT_ID:-}"
TITLE="${VITE_TITLE:-Agience}"
FAVICON="${VITE_FAVICON:-/favicon.ico}"

cat > /usr/share/nginx/html/config.js <<EOF
window.__AGIENCE_CONFIG__ = Object.freeze({
  backendUri: "$(json_escape "$BACKEND_URI")",
  clientId: "$(json_escape "$CLIENT_ID")",
  title: "$(json_escape "$TITLE")",
  favicon: "$(json_escape "$FAVICON")"
});
EOF