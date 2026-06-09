"""Internal `/internal/*` endpoints — kernel-service callers only.

- ``GET /internal/personas`` — Chorus calls this at startup to resolve
  its persona slugs to the deployment's randomly-assigned UUIDs.
- ``GET /internal/mcp-client?client_id=…`` — Origin calls this during
  OAuth ``/authorize`` and ``/token`` to look up the redirect URIs and
  allowed OAuth scopes for a registered ``vnd.agience.mcp-client+json``
  artifact (its ``context.client_id`` matches the OAuth ``client_id``
  parameter).

Auth: kernel mutual-JWT only (``principal_type=service``, ``iss in
{chorus, origin}``). These endpoints deliberately bypass user-grant
gating because they serve the bootstrap maps the gateway and OAuth
flow need *before* they can route any user request — no
chicken-and-egg.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose.exceptions import JWTError

from db import arango as db_arango
from kernel import authority_trust
from services import server_registry
from services.bootstrap_types import SERVER_ARTIFACT_SLUG_PREFIX
from services.dependencies import get_arango_db
from services.platform_topology import get_id_optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["Internal (kernel service)"], include_in_schema=False)

_bearer = HTTPBearer(auto_error=False)


def _require_kernel_service(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Verify caller is a kernel service. Returns the calling service name."""
    if not credentials or not credentials.credentials:
        raise HTTPException(401, "Missing bearer token")

    last_err: Optional[Exception] = None
    for issuer in ("chorus", "origin"):
        try:
            payload = authority_trust.verify_service_jwt(
                credentials.credentials,
                expected_issuer=issuer,
                expected_audience="mantle",
            )
        except (KeyError, JWTError) as exc:
            last_err = exc
            continue
        if payload.get("principal_type") == "service":
            return issuer
    raise HTTPException(401, f"Invalid kernel JWT: {last_err}")


@router.get("/personas")
def list_personas(_caller: str = Depends(_require_kernel_service)) -> dict:
    """Return the deployment's slug→UUID map for first-party persona artifacts.

    Source of truth: `services.server_registry.all_client_ids()` — the manifest
    of personas built into this Mantle image. UUIDs come from `platform_topology`
    where they were generated and persisted at first boot.

    Response shape:
        {
          "personas": [
            { "slug": "aria",  "client_id": "agience-server-aria",  "artifact_id": "<uuid>" },
            ...
          ]
        }
    """
    personas: list[dict] = []
    for client_id in sorted(server_registry.all_client_ids()):
        # client_id == "agience-server-{slug}" — match SERVER_ARTIFACT_SLUG_PREFIX format.
        slug = client_id.replace(SERVER_ARTIFACT_SLUG_PREFIX, "", 1) if client_id.startswith(SERVER_ARTIFACT_SLUG_PREFIX) else client_id
        artifact_slug = f"{SERVER_ARTIFACT_SLUG_PREFIX}{slug}"
        artifact_id = get_id_optional(artifact_slug)
        if not artifact_id:
            logger.warning("No artifact id for persona slug %s — skipping", artifact_slug)
            continue
        personas.append({
            "slug": slug,
            "client_id": client_id,
            "artifact_id": artifact_id,
        })
    return {"personas": personas}


_MCP_CLIENT_CONTENT_TYPE = "application/vnd.agience.mcp-client+json"


@router.get("/mcp-client")
def find_mcp_client(
    client_id: str = Query(..., description="OAuth client_id to resolve"),
    db: StandardDatabase = Depends(get_arango_db),
    _caller: str = Depends(_require_kernel_service),
) -> dict:
    """Look up an MCP Client artifact by its OAuth ``client_id``.

    Returns the registered redirect URIs and allowed OAuth scopes for use
    by Origin's ``/authorize`` and ``/token`` endpoints.

    The MCP Client is a ``vnd.agience.mcp-client+json`` artifact; its
    ``context.client_id`` is the OAuth identifier. Multiple artifacts
    *should not* share a client_id; if they do (operator misconfiguration)
    the most recently created non-archived row wins.

    Returns 404 if no matching artifact exists.
    """
    if not client_id or not client_id.strip():
        raise HTTPException(400, "client_id is required")

    # AQL has no JSON.parse — pull all candidate non-archived rows and filter
    # by context.client_id in Python below.
    cursor = db.aql.execute(
        """
        FOR a IN @@col
          FILTER a.content_type == @ct AND a.state != "archived"
          SORT a.created_time DESC
          RETURN a
        """,
        bind_vars={"@col": db_arango.COLLECTION_ARTIFACTS, "ct": _MCP_CLIENT_CONTENT_TYPE},
    )

    for doc in cursor:
        ctx = doc.get("context")
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except (TypeError, ValueError):
                continue
        if not isinstance(ctx, dict):
            continue
        if (ctx.get("client_id") or "").strip() != client_id.strip():
            continue
        redirect_uris = ctx.get("redirect_uris") or []
        allowed_oauth_scopes = ctx.get("allowed_oauth_scopes") or []
        return {
            "artifact_id": doc.get("_key"),
            "client_id": ctx.get("client_id"),
            "redirect_uris": [str(u) for u in redirect_uris if u],
            "allowed_oauth_scopes": [str(s) for s in allowed_oauth_scopes if s],
        }

    raise HTTPException(404, f"No MCP Client artifact registered for client_id={client_id!r}")
