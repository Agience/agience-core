#!/bin/sh
# Renders the SPA's runtime config (window.__AGIENCE_CONFIG__) from container env
# at startup, so ONE built image serves any domain. nginx:alpine runs every
# /docker-entrypoint.d/*.sh before starting nginx, and nginx.conf serves
# /config.js no-cache so a redeploy is picked up immediately.
#
# The emitted KEYS must match src/facet/src/config/runtime.ts:
#   originUri  — Origin (auth / identity / OIDC / setup)        e.g. https://my.agience.ai
#   mantleUri  — Mantle (artifacts / search / events)           e.g. https://my.agience.ai/api
#   backendUri — legacy alias for mantleUri (runtime.ts falls back to it)
#   clientId, title, favicon
#
# Reads the VITE_-prefixed names the compose passes (build-time names reused as
# runtime env), falling back to bare names, then to local-dev ports.
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

ORIGIN_URI="${VITE_ORIGIN_URI:-${ORIGIN_URI:-http://localhost:8080}}"
MANTLE_URI="${VITE_MANTLE_URI:-${MANTLE_URI:-${VITE_BACKEND_URI:-http://localhost:8081}}}"
CLIENT_ID="${VITE_CLIENT_ID:-${CLIENT_ID:-platform}}"
TITLE="${VITE_TITLE:-${TITLE:-Agience}}"
FAVICON="${VITE_FAVICON:-${FAVICON:-/favicon.png}}"

cat > /usr/share/nginx/html/config.js <<EOF
window.__AGIENCE_CONFIG__ = Object.freeze({
  originUri: "$(json_escape "$ORIGIN_URI")",
  mantleUri: "$(json_escape "$MANTLE_URI")",
  backendUri: "$(json_escape "$MANTLE_URI")",
  clientId: "$(json_escape "$CLIENT_ID")",
  title: "$(json_escape "$TITLE")",
  favicon: "$(json_escape "$FAVICON")"
});
EOF
