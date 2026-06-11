import json
import logging
import logging.config
import time
from pathlib import Path


class RedactAccessQueryFilter(logging.Filter):
    """Remove query strings from uvicorn access logs.

    Uvicorn's access logger includes the raw request target, which can contain
    sensitive query parameters (OAuth `code`, share tokens, etc.). Strip the
    query string so these values never land in stdout logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            args = record.args
            # Uvicorn access log args: (client_addr, method, path, http_version, status_code)
            # Uvicorn error WebSocket args: (client_addr, path_with_query, status)
            # Scan all tuple elements and strip query strings from any that look
            # like URL paths (start with "/" and contain "?").
            if not isinstance(args, tuple):
                return True
            new_args = list(args)
            changed = False
            for i, arg in enumerate(new_args):
                if isinstance(arg, str) and arg.startswith("/") and "?" in arg:
                    new_args[i] = arg.split("?", 1)[0]
                    changed = True
            if changed:
                record.args = tuple(new_args)
        except Exception:
            # Never break logging.
            pass
        return True


class UTCFormatter(logging.Formatter):
    """Logging formatter that renders %(asctime)s in UTC."""

    converter = time.gmtime
<<<<<<< Updated upstream
=======


# Request-line fragments whose uvicorn.access records are pure noise and should
# never reach stdout:
#   - health probes — docker/k8s hit these every few seconds, forever
#   - chat streaming — dozens of POST /events/emit per turn
# Matched against the quoted request target ('"GET /version ') so that, e.g.,
# "/version" never suppresses an unrelated "/versions" path.
_SUPPRESSED_REQUEST_LINES = (
    '"GET /version ',
    '"HEAD /version ',
    '"GET /status ',
    '"HEAD /status ',
    '"GET /healthz ',
    '"HEAD /healthz ',
    '"POST /events/emit ',
)


class SuppressNoisyAccessFilter(logging.Filter):
    """Drop high-frequency, uninformative request lines from uvicorn access logs.

    Health-check probes and chat delta emits would otherwise bury every useful
    access-log entry. This only suppresses the *log line* — the requests still
    run, so liveness checks are unaffected.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            # Never break logging.
            return True
        return not any(frag in msg for frag in _SUPPRESSED_REQUEST_LINES)


# ---------------------------------------------------------------------------
# Shared logging config
# ---------------------------------------------------------------------------
# `uvicorn_log_config.json` (this file's sibling) is the SINGLE source of truth
# for log formatting. It is consumed two ways:
#   1. The Docker CMD passes it to uvicorn via `--log-config` (origin/mantle).
#   2. `configure_logging()` applies the same dict in-process at app import.
# (2) is the reliable path: uvicorn configures its own loggers in
# `Config.__init__`, which runs BEFORE the app module is imported, so a
# dictConfig at import time wins and stamps timestamps onto uvicorn's own
# startup + access lines — even when the `--log-config` flag never reaches the
# server (e.g. chorus calls `uvicorn.run()` directly, or an image predates the
# flag). `disable_existing_loggers` is false in the JSON, so loggers created by
# earlier imports (kernel.*, services.*) keep working.
_LOG_CONFIG_PATH = Path(__file__).resolve().parent / "uvicorn_log_config.json"


def build_log_config() -> dict:
    """Return the shared logging dictConfig parsed from the sibling JSON."""
    return json.loads(_LOG_CONFIG_PATH.read_text(encoding="utf-8"))


def configure_logging() -> None:
    """Apply the shared logging config in-process. Safe to call at import."""
    logging.config.dictConfig(build_log_config())
>>>>>>> Stashed changes
