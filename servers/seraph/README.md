# agience-server-seraph

Status: **Draft** — design phase; implementation begins Phase 1j
Date: 2026-03-05

**Domain**: Security, Governance & Trust — access control, audit trails, identity verification, policy compliance, cryptographic signing

---

## Responsibility

Seraph is the guardian layer of the Agience platform. It enforces access policies, maintains a tamper-evident audit trail of all security events, verifies identities and tokens, ensures governance policy compliance, and enables cryptographic signing of knowledge artifacts.

---

## Tool Surface

| Tool | Status | Description |
|---|---|---|
| `audit_access` | 🔲 Phase 1j | Query the access audit log for a resource, collection, or user |
| `check_permissions` | 🔲 Phase 1j | Check what a person or API key can access |
| `grant_access` | 🔲 Phase 1j | Grant access to a collection for a person or team |
| `revoke_access` | 🔲 Phase 1j | Revoke access to a collection |
| `rotate_api_key` | 🔲 Phase 1j | Rotate a scoped API key and return the new key |
| `verify_token` | 🔲 Phase 1j | Verify a JWT or API key and return its decoded claims |
| `list_audit_events` | 🔲 Phase 1j | List recent security events (logins, grants, revocations) |
| `sign_card` | 🔲 Phase 1j | Create a tamper-evident cryptographic signature artifact (tool name pending rename) |
| `enforce_policy` | 🔲 Phase 1j | Evaluate a request or artifact against system policies |
| `list_policies` | 🔲 Phase 1j | List active governance policies |
| `check_compliance` | 🔲 Phase 1j | Check compliance of a resource or workflow |

---

## Auth

| Env var | Description |
|---|---|
| `AGIENCE_API_KEY` | Platform API key (Bearer token) |
| `AGIENCE_API_URI` | Base URI of the agience-core backend |
| `MCP_PORT` | HTTP port for the MCP server (default: `8089`) |

---

## Quick Start

```bash
pip install -e .
export AGIENCE_API_KEY=<your-key>
export AGIENCE_API_URI=https://api.yourdomain.com
python server.py
```

---

## Target Repo

`github.com/Agience/agience-server-seraph` (public)
