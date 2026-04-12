#!/usr/bin/env bash
set -euo pipefail

: "${BACKEND_URI:=http://servers:8082/astra}"
: "${STREAM_CONF:=/etc/srs/srs.conf}"
: "${STREAM_HLS_FRAGMENT:=4}"
: "${STREAM_HLS_WINDOW:=60}"
: "${STREAM_WEBHOOK_PUBLISH_PATH:=/stream/publish}"
: "${STREAM_WEBHOOK_UNPUBLISH_PATH:=/stream/unpublish}"

export STREAM_WEBHOOK_PUBLISH="${BACKEND_URI}${STREAM_WEBHOOK_PUBLISH_PATH}"
export STREAM_WEBHOOK_UNPUBLISH="${BACKEND_URI}${STREAM_WEBHOOK_UNPUBLISH_PATH}"

mkdir -p "$(dirname "$STREAM_CONF")" /var/stream

cat > "$STREAM_CONF" <<CONF
listen                  0.0.0.0:1936;
max_connections         1000;
daemon                  on;
srs_log_tank            file;
srs_log_file            /dev/stdout;

http_server {
  enabled       on;
  listen        0.0.0.0:1985;
  dir           /var/stream;
}

vhost __defaultVhost__ {
  hls {
    enabled         on;
    hls_fragment    ${STREAM_HLS_FRAGMENT};
    hls_window      ${STREAM_HLS_WINDOW};
    hls_cleanup     on;
    hls_path        /var/stream;
    hls_m3u8_file   [app]/[stream]/index.m3u8;
    hls_ts_file     [app]/[stream]/[seq].ts;
  }

  http_hooks {
    enabled         on;
    on_publish      ${STREAM_WEBHOOK_PUBLISH};
    on_unpublish    ${STREAM_WEBHOOK_UNPUBLISH};
  }
}
CONF

exec /usr/local/srs/objs/srs -c "$STREAM_CONF"
