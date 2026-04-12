# Agience Server Auth — Shared Module

Status: **Reference**
Date: 2026-04-02

## Overview

`agience_server_auth.py` provides the canonical authentication framework for all Agience MCP servers. Every server imports `AgieceServerAuth` from this module — no server implements its own JWKS fetch, JWT verification, RSA key management, or middleware.

## Architecture

```
Core (auth_service.py)                     MCP Server (_shared/agience_server_auth.py)
┌────────────────────┐                     ┌──────────────────────────────────────┐
│ Signs delegation   │  ─── RS256 JWT ───▷ │ Verifies via JWKS (aud + expiry)    │
│ JWTs (RFC 8693)    │                     │ Stores in per-request ContextVar     │
│                    │                     │                                      │
│ Wraps secrets in   │  ─── JWE ────────▷ │ Decrypts with RSA-OAEP-256 private  │
│ RSA-OAEP-256 JWE   │                     │ key (seraph only)                    │
│                    │                     │                                      │
│ Publishes JWKS at  │  ◁── GET ────────── │ Fetches at startup + refresh on      │
│ /.well-known/jwks  │                     │ verification failure (rate-limited)   │
│                    │                     │                                      │
│ Stores server JWK  │  ◁── PUT ────────── │ Registers RSA public key at startup  │
│ for JWE wrapping   │                     │                                      │
└────────────────────┘                     └──────────────────────────────────────┘
```

## Usage Pattern

Every server follows this exact pattern:

```python
from agience_server_auth import AgieceServerAuth as _AgieceServerAuth

_auth = _AgieceServerAuth(SERVER_CLIENT_ID, AGIENCE_API_URI)

# Auth wrappers
async def _user_headers() -> dict[str, str]:
    return await _auth.user_headers(_exchange_token)

def _get_delegation_user_id() -> str:
    return _auth.get_delegation_user_id()

# Standard server interface
def create_server_app():
    return _auth.create_app(mcp, _exchange_token)

async def server_startup() -> None:
    await _auth.startup(_exchange_token)
```

## Key Concepts

### Delegation JWTs (RFC 8693)

Core issues short-lived (300s) delegation tokens when proxying user requests to MCP servers:

| Claim | Value |
|-------|-------|
| `sub` | User ID (the human whose request this represents) |
| `aud` | Target server's `client_id` (e.g., `agience-server-aria`) |
| `act.sub` | Server's `client_id` (the actor performing on behalf of user) |
| `principal_type` | `"delegation"` |
| `iss` | Core authority issuer |
| `exp` | Short TTL (300 seconds) |

Servers verify `aud == self.client_id` to ensure the token was issued **to them** — not forwarded from another server.

### Server Identity (`_exchange_token`)

Each server has a `client_credentials` token exchange for its own platform identity. This is used for:
- Registering the server's RSA public key with Core
- Background/startup API calls with no user context
- Fallback when no delegation JWT is available

The token is cached with 60-second refresh buffer.

### Two JWT Verification Methods

Both methods use `python-jose` for RS256 signature verification with automatic `kid` matching against the cached JWKS.

| Method | Checks | Used By |
|--------|--------|--------|
| `verify_delegation_jwt()` | RS256 signature (via JWKS, `kid` matched) + `aud` + `principal_type=delegation` + expiry | All servers (via middleware) |
| `verify_core_jwt()` | RS256 signature (via JWKS, `kid` matched) + expiry; **rejects** delegation tokens | Ophan (operator tokens) |

### JWE Secret Delivery

Seraph fetches encrypted secrets from Core via `POST /secrets/fetch`. Core wraps each secret in a JWE envelope (RSA-OAEP-256 + AES-256-GCM) using the server's registered public key. Only the target server can decrypt.

### `_user_headers()` vs `_headers()`

| Function | Returns | Use When |
|----------|---------|----------|
| `_user_headers()` | Delegation JWT (user context) or fallback server token | Calling Core on behalf of a user |
| `_headers()` | Server's own platform token | Server-identity calls (startup, background) |

## Rules

1. **Never pass tokens as tool arguments** — tokens flow via middleware ContextVar
2. **Never log tokens or secrets** — log events, not credentials
3. **Never import Core's `auth_service` directly** — use `AgieceServerAuth`
4. **Never duplicate auth code** — all auth logic lives here
5. **Every server registers its RSA public key at startup** — required for JWE delivery
6. **`aud` claim prevents token forwarding** — a token issued to server A cannot be used by server B
7. **JWT verification uses `python-jose`** — never hand-roll JWT parsing or signature verification
