"""Minimal example for an Agience docker-host.

Demonstrates the smallest useful host: boots the connection, exposes a single
HTTP endpoint, and uses the connection to look up an artifact in Mantle.

Replace this file with your real entrypoint. Keep `boot()` at startup; keep
`verify_service_caller(...)` (or `verify_delegation_caller(...)`) on every
inbound request that needs trust.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request

from connection_api import AgienceConnection

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("agience-docker-host")

connection = AgienceConnection()


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection.boot()
    yield
    connection.close()


app = FastAPI(lifespan=lifespan)


def require_caller(request: Request) -> dict:
    """Require an inbound peer-service JWT from Mantle.

    Adjust `from_issuer` to whatever service is permitted to call this host.
    For multi-source acceptance, decode the unverified header, read the issuer
    hint, then dispatch to the right `from_issuer` value.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        return connection.verify_service_caller(token, from_issuer="mantle")
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": connection._service_name}


@app.get("/artifacts/{artifact_id}")
def fetch_artifact(artifact_id: str, _claims: dict = Depends(require_caller)) -> dict:
    artifact = connection.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
