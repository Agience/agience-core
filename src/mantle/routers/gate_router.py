"""Internal gate endpoints — called by kernel MCP servers only.

Ophan pushes numeric limits after Stripe subscription events.
Ophan reads usage for the billing settings UI.

Authentication (Phase C): Chorus kernel JWT signed with `chorus.private.pem`.
Verified via the inline JWKS in the platform authority manifest.
Caller must have `principal_type=service`, `iss=chorus`, `sub` (the persona
client_id) ∈ server_registry.all_client_ids(), and `aud=mantle`.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from arango.database import StandardDatabase
from jose.exceptions import JWTError

from services import server_registry
from kernel import authority_trust
from services.dependencies import get_arango_db
from services import gate_service

logger = logging.getLogger(__name__)

gate_router = APIRouter(prefix="/internal/gate", tags=["Gate (internal)"])

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth: chorus kernel JWT only
# ---------------------------------------------------------------------------

def _require_kernel_server(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Verify caller is a first-party Chorus persona. Returns the persona client_id."""
    if not credentials or not credentials.credentials:
        raise HTTPException(401, "Missing bearer token")

    try:
        payload = authority_trust.verify_service_jwt(
            credentials.credentials,
            expected_issuer="chorus",
            expected_audience="mantle",
        )
    except (KeyError, JWTError):
        raise HTTPException(401, "Invalid kernel JWT")

    if payload.get("principal_type") != "service":
        raise HTTPException(403, "Kernel service token required")

    client_id = payload.get("sub") or payload.get("client_id")
    if not client_id or client_id not in server_registry.all_client_ids():
        raise HTTPException(403, "Not a recognized kernel persona")

    return client_id


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SetLimitsRequest(BaseModel):
    person_id: str
    max_workspaces: Optional[int] = None
    max_artifacts: Optional[int] = None
    vu_limit: Optional[int] = None
    features: Optional[list[str]] = None   # capability flags (e.g. ["beacon"]); omit to leave unchanged


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@gate_router.post("/set-limits", status_code=204)
def set_limits(
    body: SetLimitsRequest,
    db: StandardDatabase = Depends(get_arango_db),
    _caller: str = Depends(_require_kernel_server),
):
    """Upsert entitlement limits for a person. Called by Ophan after Stripe events."""
    gate_service.set_limits(
        db, body.person_id,
        max_workspaces=body.max_workspaces,
        max_artifacts=body.max_artifacts,
        vu_limit=body.vu_limit,
        features=body.features,
    )
    logger.info(
        "Gate limits updated: person=%s caller=%s features=%s",
        body.person_id, _caller, body.features if body.features is not None else "(unchanged)",
    )
    return Response(status_code=204)


@gate_router.get("/usage/{person_id}")
def get_usage(
    person_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    _caller: str = Depends(_require_kernel_server),
):
    """Return limits + current usage for a person. Called by Ophan for the billing UI."""
    limits = gate_service.get_or_default_limits(db, person_id)
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "person_id": person_id,
        "limits": limits,
        "usage": {
            "workspaces": gate_service.count_workspaces(db, person_id),
            "artifacts": gate_service.count_artifacts(db, person_id),
            "vu": gate_service.get_tally(db, person_id, "vu", current_month),
        },
    }
