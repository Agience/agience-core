"""Unit tests for ``mcp_client/security.py`` -- SSRF, header, stdio checks."""
from __future__ import annotations

from unittest.mock import patch
import socket

import pytest

from mcp_client.security import (
    SSRFError,
    sanitize_headers,
    validate_stdio_transport,
    validate_url,
)


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------

class TestValidateUrl:
    def test_rejects_non_http_schemes(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url("ftp://example.com/file")

    def test_rejects_missing_hostname(self):
        with pytest.raises(ValueError, match="Missing hostname"):
            validate_url("http:///path")

    @patch("core.config.ALLOW_LOCAL_MCP_SERVERS", True)
    def test_allows_private_when_local_enabled(self):
        result = validate_url("http://192.168.1.1:8080/mcp")
        assert result == "http://192.168.1.1:8080/mcp"

    @patch("core.config.ALLOW_LOCAL_MCP_SERVERS", False)
    @patch("mcp_client.security.socket.getaddrinfo")
    def test_blocks_private_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 8080)),
        ]
        with pytest.raises(SSRFError, match="blocked address"):
            validate_url("http://evil.internal:8080/mcp")

    @patch("core.config.ALLOW_LOCAL_MCP_SERVERS", False)
    @patch("mcp_client.security.socket.getaddrinfo")
    def test_blocks_loopback(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
        ]
        with pytest.raises(SSRFError, match="blocked address"):
            validate_url("http://localhost/mcp")

    @patch("core.config.ALLOW_LOCAL_MCP_SERVERS", False)
    @patch("mcp_client.security.socket.getaddrinfo")
    def test_allows_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]
        result = validate_url("https://example.com/mcp")
        assert result == "https://example.com/mcp"

    @patch("core.config.ALLOW_LOCAL_MCP_SERVERS", False)
    @patch("mcp_client.security.socket.getaddrinfo", side_effect=socket.gaierror("DNS fail"))
    def test_dns_failure(self, _):
        with pytest.raises(SSRFError, match="DNS resolution failed"):
            validate_url("http://nonexistent.invalid/mcp")


# ---------------------------------------------------------------------------
# sanitize_headers
# ---------------------------------------------------------------------------

class TestSanitizeHeaders:
    def test_passes_allowed_headers(self):
        raw = {
            "Authorization": "Bearer tok",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        result = sanitize_headers(raw)
        assert "Authorization" in result
        assert "Content-Type" in result
        assert "Accept" in result

    def test_blocks_dangerous_headers(self):
        raw = {
            "Authorization": "Bearer tok",
            "Cookie": "session=abc",
            "X-Forwarded-For": "10.0.0.1",
            "Host": "evil.com",
        }
        result = sanitize_headers(raw)
        assert "Authorization" in result
        assert "Cookie" not in result
        assert "X-Forwarded-For" not in result
        assert "Host" not in result

    def test_empty_input(self):
        assert sanitize_headers(None) == {}
        assert sanitize_headers({}) == {}

    def test_unknown_headers_removed(self):
        raw = {"X-Random-Custom": "value"}
        result = sanitize_headers(raw)
        assert "X-Random-Custom" not in result


# ---------------------------------------------------------------------------
# validate_stdio_transport
# ---------------------------------------------------------------------------

class TestValidateStdioTransport:
    def test_reject_when_not_allowed(self):
        with pytest.raises(ValueError, match="not permitted"):
            validate_stdio_transport("npx", allow_stdio=False)

    def test_allowed_commands(self):
        for cmd in ("npx", "uvx", "python", "python3", "node", "deno"):
            validate_stdio_transport(cmd, allow_stdio=True)

    def test_blocked_commands(self):
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_stdio_transport("bash", allow_stdio=True)

        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_stdio_transport("curl", allow_stdio=True)

    def test_strips_path_prefix(self):
        validate_stdio_transport("/usr/bin/python3", allow_stdio=True)
        validate_stdio_transport("C:\\Python\\python.exe", allow_stdio=True)

    def test_command_with_args(self):
        # Should check only the base command, not arguments
        validate_stdio_transport("npx -y @modelcontextprotocol/server", allow_stdio=True)
