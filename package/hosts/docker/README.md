# Agience Docker Host

Status: **Draft**
Date: 2026-05-08

Reference shell for building a containerized service that connects to Agience as a trusted internal peer. This is the framework Chorus itself follows — copy this directory and adapt it for your own MCP server, daemon, or background worker.

A docker-host is the deployable form factor when you want to run MCP servers (or other Agience-aware services) inside a container that authenticates to Origin/Mantle/Chorus over the same mutual-JWT trust mesh used by first-party services.

If you want a local desktop daemon instead, see `../desktop/`.
If you want a browser extension that calls Agience over HTTP API key, see `../browser/`.

---

## What's in here

| File | Purpose |
|------|---------|
| `Dockerfile.template` | Reference Dockerfile — copies `src/kernel/` and bakes a service identity into the image |
| `connection_api.py` | Reusable `AgienceConnection` — boots service identity, signs outbound JWTs, calls Mantle/Origin |
| `example_main.py` | Minimal FastAPI app demonstrating one outbound call against Mantle |
| `pyproject.toml` | Package metadata for the example |
| `requirements.txt` | Runtime dependencies |

---

## Trust model

Every docker-host runs as a **service principal** with its own RSA keypair. The keypair lives at `KEYS_DIR/<service>.private.pem` inside the container; its public key is published in the platform authority manifest at `KEYS_DIR/authority.manifest.json` (mounted from a shared secrets volume).

On boot the host calls `init_service_identity("<service>")` from the kernel. From then on:

- Outbound calls to Mantle/Origin/Chorus are signed with `service_identity.sign_service_jwt(audience=...)`.
- Inbound calls are verified against the inline JWKS in the authority manifest via `authority_trust.verify_jwt(...)`.

There is no shared secret. Each peer trusts every other peer because they're all signed by keys listed in the same manifest.

---

## Quick start

```bash
# 1. Copy this directory
cp -r package/hosts/docker my-host
cd my-host

# 2. Build
docker build -f Dockerfile.template -t my-host:dev ..

# 3. Run alongside the Agience stack
docker run --rm \
  --network agience_default \
  -v agience_keys:/keys:ro \
  -e KEYS_DIR=/keys \
  -e AGIENCE_API_URI=http://mantle:8081 \
  -e ORIGIN_URI=http://origin:8080 \
  my-host:dev
```

The mounted `/keys` volume must contain `<service>.private.pem` (your host's signing key) and `authority.manifest.json` (the platform trust anchors). The Agience installer's `package/docker/init.py` provisions both.

---

## Anatomy of `connection_api.py`

`AgienceConnection` is the only class you need:

```python
from connection_api import AgienceConnection

conn = AgienceConnection(service_name="my-host")
conn.boot()                                 # loads service identity
artifact = conn.get_artifact(server_id)     # signed Mantle call
allowed = conn.can_invoke(principal_id, server_id)  # Origin grant check
```

It bundles:

- `init_service_identity` — loads `<service>.private.pem` and registers the signer
- `sign_service_jwt(audience=...)` — short-lived RS256 token for the named peer
- A small `httpx.Client` with caches for artifact and grant lookups
- Helpers for the most common calls (`/artifacts/{id}`, `/auth/grants/check`, `/internal/personas`)

If your host needs more endpoints, extend the class — keep it boring. The point is fail-fast HTTP with mutual JWT, not a full SDK.

---

## When NOT to use this

- You're calling Agience as an external user → use a personal API key against the public `/mcp` endpoint, not service identity.
- You're running on the user's own machine → use `../desktop/` (relay companion) instead.
- You're inside a browser tab → use `../browser/` (extension shell) instead.
