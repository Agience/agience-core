"""Beacon add-on callback surface — premium, capability-gated.

The **anchors themselves are platform data** and stay open across the API —
nothing here gates *access* to anchors. What these endpoints gate is the
**Beacon analysis interaction**: reading the live AnchorSet matrix for off-path
analysis by the Beacon add-on, and writing the Beacon-computed profile back.
Both require the caller's account to be entitled to the ``beacon`` capability
(`gate_service.has_feature`), keyed off the user identity carried by the
forwarded delegation token.

Beacon runs as a separate, closed MCP server (its own repo). It calls these
endpoints with the user's delegation JWT (the same inbound-token pattern the
Chorus personas use), so the gate is enforced here on the user — Core never
trusts the add-on to self-authorize. When billing enforcement is off (dev /
self-host) the gate is open, so the local stack works without Beacon at all.

The profile Beacon returns is treated as **opaque** here: Core stores and serves
it without interpreting the add-on's metrics. Geometry stays non-authorizing
(canonical plan §1): these endpoints expose the plaintext anchor matrix and
accept a derived profile; they never touch cell keys, the oracle, or the
light-cone.
"""

import logging
from typing import Optional

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from services import gate_service
from services.dependencies import AuthContext, get_arango_db, get_auth

logger = logging.getLogger(__name__)

beacon_router = APIRouter(prefix="/internal/beacon", tags=["Beacon (premium)"])

_BEACON_FEATURE = "beacon"

# Process-local store for the most recently applied Beacon profile. Persisting it
# durably (and having the open density layer consume it) is the next wire; for
# now the add-on can write and re-read its profile within a running instance.
_beacon_profile: dict = {}


def require_beacon(
    auth: AuthContext = Depends(get_auth),
    db: StandardDatabase = Depends(get_arango_db),
) -> str:
    """Gate: the authenticated user must be entitled to the ``beacon`` capability.

    Returns the person_id on success. Raises 401 without a user identity, 403
    when the account lacks the Beacon add-on.
    """
    person_id = auth.user_id or (auth.principal_id if auth.principal_type == "user" else None)
    if not person_id:
        raise HTTPException(status_code=401, detail="User identity required for Beacon")
    if not gate_service.has_feature(db, person_id, _BEACON_FEATURE):
        raise HTTPException(status_code=403, detail="Beacon add-on not entitled for this account")
    return person_id


class BeaconProfile(BaseModel):
    """A profile the Beacon add-on computes over the manifold and writes back.

    The contents are opaque to Core — it stores and serves them without
    interpreting the add-on's metrics.
    """
    model_id: Optional[str] = None
    thresholds: Optional[dict] = None
    metrics: Optional[dict] = None
    proposals: Optional[list] = None


@beacon_router.get("/anchorset")
def read_anchorset(_person_id: str = Depends(require_beacon)):
    """Return the live AnchorSet (model, dim, labels, unit-norm matrix) for the
    Beacon add-on to analyze. Premium interaction, hence gated — the anchors are
    open elsewhere, but feeding them to the Beacon add-on is the premium part."""
    from search.anchors import get_live_anchorset

    aset = get_live_anchorset()
    if aset is None or aset.matrix is None or len(aset) < 2:
        raise HTTPException(status_code=409, detail="No live AnchorSet available to analyze")
    return {
        "model_id": aset.model_id,
        "dim": aset.dim,
        "labels": [a.label for a in aset.anchors],
        "anchor_ids": [a.anchor_id for a in aset.anchors],
        "matrix": aset.matrix.astype(float).tolist(),
    }


@beacon_router.post("/profile", status_code=204)
def apply_profile(
    body: BeaconProfile,
    person_id: str = Depends(require_beacon),
):
    """Accept a Beacon-computed profile and hold it for this instance. The
    metrics are opaque to Core."""
    global _beacon_profile
    _beacon_profile = body.model_dump()
    logger.info(
        "Beacon profile applied by person=%s (model=%s, thresholds=%s, proposals=%d)",
        person_id, body.model_id, bool(body.thresholds), len(body.proposals or []),
    )
    return Response(status_code=204)


@beacon_router.get("/profile")
def get_profile(_person_id: str = Depends(require_beacon)):
    """Return the most recently applied Beacon profile (empty object if none)."""
    return _beacon_profile
