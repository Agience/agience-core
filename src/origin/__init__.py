"""Origin — identity, OIDC, grants, passkeys, OTP, API keys, server credentials.

Step 1 of the four-container migration. See `.dev/features/four-container-architecture.md`
for the spec and `.dev/features/four-container-step-1-plan.md` for the implementation plan.

Origin runs as a separate FastAPI process from the existing monolith (Mantle).
It owns Postgres for identity-tier state and is the sole issuer of JWTs.
"""
