"""MCP client security -- SSRF protection, header allowlist, command restrictions.

This module centralises all validation that must happen before the platform
connects to a third-party MCP server on behalf of a user.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

from core import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSRF -- blocked IP networks (RFC 1918, link-local, loopback, ULA)
# ---------------------------------------------------------------------------
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if *ip_str* falls within a blocked network range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> block
    return any(addr in net for net in _BLOCKED_NETWORKS)


class SSRFError(Exception):
    """Raised when a URL targets a blocked network."""


def validate_url(url: str) -> str:
    """Validate a URL is safe to connect to.

    Performs hostname resolution and checks the resolved IP against blocked
    network ranges. Returns the validated URL unchanged on success.

    Raises ``SSRFError`` if the URL targets a private/internal address.
    Raises ``ValueError`` for malformed URLs.

    When ``ALLOW_LOCAL_MCP_SERVERS`` is ``True`` (dev/local mode), private
    network checks are skipped.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Missing hostname in URL: {url!r}")

    if config.ALLOW_LOCAL_MCP_SERVERS:
        return url

    # Resolve hostname to IP and check
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname!r}: {exc}")

    for family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            raise SSRFError(
                f"URL {url!r} resolves to blocked address {ip_str}"
            )

    return url


# ---------------------------------------------------------------------------
# Header allowlist -- only permit safe HTTP headers
# ---------------------------------------------------------------------------
_ALLOWED_HEADER_NAMES = frozenset({
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-custom-header",
    "accept",
    "content-type",
    "user-agent",
})

_BLOCKED_HEADER_NAMES = frozenset({
    "host",
    "cookie",
    "set-cookie",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "forwarded",
    "connection",
    "transfer-encoding",
    "content-length",
    "te",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
})


def sanitize_headers(headers: Optional[dict]) -> dict:
    """Filter a header dict, removing blocked and unknown header names.

    Returns a new dict containing only allowed headers. Logs warnings for
    any headers that were removed.
    """
    if not headers:
        return {}

    safe: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower().strip()
        if lower in _BLOCKED_HEADER_NAMES:
            logger.warning("Blocked MCP header removed: %s", name)
            continue
        if lower not in _ALLOWED_HEADER_NAMES:
            logger.warning("Unknown MCP header removed: %s", name)
            continue
        safe[name] = value
    return safe


# ---------------------------------------------------------------------------
# Stdio command restrictions
# ---------------------------------------------------------------------------
_ALLOWED_STDIO_COMMANDS = frozenset({
    "npx",
    "uvx",
    "python",
    "python3",
    "node",
    "deno",
})


def validate_stdio_transport(
    command: str,
    allow_stdio: bool = False,
) -> None:
    """Validate that a stdio transport command is allowed.

    Raises ``ValueError`` if:
    - ``allow_stdio`` is False (cloud mode -- stdio transports not permitted).
    - The command is not in the allowed command list.
    """
    if not allow_stdio:
        raise ValueError(
            "Stdio transport is not permitted in this deployment. "
            "Only HTTP/HTTPS transports are allowed."
        )

    base_command = command.split()[0] if command else ""
    # Strip path and extension -- only check the binary name
    base_command = base_command.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Remove common executable extensions
    for ext in (".exe", ".cmd", ".bat"):
        if base_command.lower().endswith(ext):
            base_command = base_command[:-len(ext)]
            break

    if base_command not in _ALLOWED_STDIO_COMMANDS:
        raise ValueError(
            f"Stdio command {command!r} is not in the allowed list: "
            f"{', '.join(sorted(_ALLOWED_STDIO_COMMANDS))}"
        )
