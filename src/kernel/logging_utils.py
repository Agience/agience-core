import logging
import time


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
