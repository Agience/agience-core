"""Stream lifecycle router — SRS webhook handlers (Core infra layer).

SRS (Simple Realtime Server) runs alongside content (MinIO) and graph
(ArangoDB) as a core infrastructure service.  It is a pure streaming
gateway — no application logic.  On publish/unpublish events SRS calls
these Mantle endpoints, which own the session artifact lifecycle.

Webhook auth model
------------------
The SRS container is reachable only from inside the Docker network and
calls these endpoints without a user token.  The stream key embedded in
the SRS payload acts as the credential:

    {source_artifact_id}:{api_key}

Mantle validates the API key through Origin and checks that the resolved
principal has read access to the source artifact.  Only then is a session
artifact created.

Endpoints
---------
POST /stream/publish      — on_publish webhook (SRS → Mantle, internal only)
POST /stream/unpublish    — on_unpublish webhook (SRS → Mantle, internal only)
GET  /stream/sessions     — list active sessions (authenticated user endpoint)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

import db.arango as arango
from entities.artifact import Artifact as ArtifactEntity
from services.dependencies import AuthContext, get_arango_db, get_auth, check_access

logger = logging.getLogger("agience.stream")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Base URL that browsers use to reach SRS HLS output.  Set this to the
# public-facing URL of the stream service (via Caddy or direct port).
# Example: https://stream.my.agience.ai  or  http://localhost:1985
STREAM_HLS_URI: str = os.getenv("STREAM_HLS_URI", "http://localhost:1985").rstrip("/")

router = APIRouter(prefix="/stream", tags=["Stream"])

# ---------------------------------------------------------------------------
# In-memory session state (guarded by _SESSION_LOCK)
# ---------------------------------------------------------------------------

_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_LOCK = asyncio.Lock()
_IDLE_WINDOW = timedelta(seconds=10)

# Validate stream key characters — alphanumeric, hyphens, underscores, colons.
_SAFE_STREAM_RE = re.compile(r"^[a-zA-Z0-9\-_:]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_session_active(entry: Dict[str, Any], now: datetime) -> bool:
    """Return True if the session is currently considered live.

    A session is active when:
    - it has never been unpublished, OR
    - it was republished after the last unpublish, OR
    - it was unpublished within the grace window (prevents flap on reconnect).
    """
    last_publish: Optional[datetime] = entry.get("last_publish")
    last_unpublish: Optional[datetime] = entry.get("last_unpublish")
    if last_publish is None:
        return False
    if last_unpublish is None:
        return True
    if last_publish > last_unpublish:
        return True
    return (now - last_unpublish) <= _IDLE_WINDOW


def _parse_stream_key(stream_name: str) -> tuple[str, str]:
    """Parse the SRS stream key into (source_artifact_id, api_key).

    SRS webhooks include the app name prefix, so the raw value is:
        ``{app}/{source_artifact_id}:{api_key}``   e.g.  ``live/abc-123:agc_xyz``

    We strip the app prefix and return (source_artifact_id, api_key).
    """
    val = (stream_name or "").strip()
    if not val:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stream key")

    # Strip SRS app name prefix (e.g. "live/") if present.
    if "/" in val:
        _app, _, remainder = val.partition("/")
        if ":" in remainder:
            val = remainder

    if ":" not in val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stream key — expected '{source_artifact_id}:{token}'",
        )
    source_artifact_id, api_key = val.split(":", 1)
    source_artifact_id = source_artifact_id.strip()
    api_key = api_key.strip()
    if not source_artifact_id or not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stream key — expected '{source_artifact_id}:{token}'",
        )
    return source_artifact_id, api_key


def _stream_key_without_app(stream_name: str) -> str:
    """Strip the SRS app prefix from a stream name (used as session dict key)."""
    val = (stream_name or "").strip()
    if "/" in val:
        _app, _, remainder = val.partition("/")
        if ":" in remainder:
            return remainder
    return val


def _hls_url(stream_key_raw: str) -> str:
    """Build the HLS playlist URL for a stream key (without app prefix).

    SRS writes HLS to:   /var/stream/live/{stream_name}/index.m3u8
    and serves it at:    {STREAM_HLS_URI}/live/{stream_name}/index.m3u8
    """
    return f"{STREAM_HLS_URI}/live/{stream_key_raw}/index.m3u8"


def _parse_context(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


# ---------------------------------------------------------------------------
# Session lifecycle (called under _SESSION_LOCK)
# ---------------------------------------------------------------------------

async def _get_or_create_session(
    stream_key: str,
    stream_name_raw: str,
    source_artifact_id: str,
    api_key: str,
    arango_db: StandardDatabase,
) -> Dict[str, Any]:
    """Return the in-memory session entry, creating a new session artifact if needed.

    Must be called under ``_SESSION_LOCK``.
    """
    now = _utcnow()
    entry = _ACTIVE_SESSIONS.get(stream_key)

    if entry is not None:
        last_unpublish: Optional[datetime] = entry.get("last_unpublish")
        if last_unpublish is None or (now - last_unpublish) <= _IDLE_WINDOW:
            entry["last_publish"] = now
            entry["last_unpublish"] = None
            logger.debug("Reusing session for stream %s", stream_key)
            return entry

    # --- Look up source artifact directly from ArangoDB ---
    source = arango.get_artifact(arango_db, source_artifact_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source artifact not found")

    workspace_id = source.collection_id
    if not workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source artifact has no workspace")

    # --- Validate API key via Origin ---
    from clients.origin_client import get_origin_client
    verify_result = get_origin_client().verify_api_key(api_key)
    if verify_result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid stream key")

    api_key_entity, grants = verify_result
    user_id = str(api_key_entity.user_id) if api_key_entity.user_id else None
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Stream key has no associated user")

    # The API key must grant at least read on the source artifact.
    has_read = any(
        (getattr(g, "resource_id", None) == source_artifact_id or
         getattr(g, "resource_id", None) == workspace_id)
        and getattr(g, "can_read", False)
        for g in grants
    )
    if not has_read:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "API key lacks read access to stream source")

    # --- Read stream config from source artifact context ---
    source_ctx = _parse_context(source.context)
    stream_cfg: dict = source_ctx.get("stream") or {}
    target_content_type: str = stream_cfg.get("target_content_type") or "application/vnd.agience.stream+json"

    # --- Create session artifact ---
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    hls = _hls_url(stream_key)
    session_ctx = json.dumps({
        "content_type": target_content_type,
        "title": f"Stream \u2014 {now_str}",
        "type": "stream-session",
        "status": "live",
        "source_artifact_id": source_artifact_id,
        "stream": {
            "hls_url": hls,
            "started_at": now.isoformat(),
        },
    })

    import uuid
    session_entity = ArtifactEntity(
        id=str(uuid.uuid4()),
        collection_id=workspace_id,
        context=session_ctx,
        content="",
        state=ArtifactEntity.STATE_DRAFT,
        created_by=user_id,
        content_type=target_content_type,
    )
    arango.create_artifact(arango_db, session_entity)
    session_artifact_id = session_entity.id

    logger.info(
        "Created session artifact %s for source %s in workspace %s",
        session_artifact_id, source_artifact_id, workspace_id,
    )

    # Append session ID to source artifact's context.stream.sessions[] list.
    sessions_list = list(stream_cfg.get("sessions") or [])
    sessions_list.append(session_artifact_id)
    updated_source_ctx = json.dumps({
        **source_ctx,
        "stream": {**stream_cfg, "sessions": sessions_list},
    })
    updated_source = ArtifactEntity.from_dict({
        **source.to_dict(),
        "context": updated_source_ctx,
    })
    arango.update_artifact(arango_db, updated_source)

    entry = {
        "workspace_id": workspace_id,
        "source_artifact_id": source_artifact_id,
        "artifact_id": session_artifact_id,
        "user_id": user_id,
        "hls_url": hls,
        "last_publish": now,
        "last_unpublish": None,
    }
    _ACTIVE_SESSIONS[stream_key] = entry
    return entry


async def _finalize_session(
    stream_key: str,
    arango_db: StandardDatabase,
) -> None:
    """Mark a session artifact as ended when SRS unpublishes.

    Must be called under ``_SESSION_LOCK``.
    """
    entry = _ACTIVE_SESSIONS.get(stream_key)
    if entry is None:
        return

    artifact_id = entry.get("artifact_id")
    workspace_id = entry.get("workspace_id")
    if not artifact_id or not workspace_id:
        return

    session = arango.get_artifact(arango_db, artifact_id)
    if session is not None:
        ctx = _parse_context(session.context)
        stream_info = ctx.get("stream") or {}
        updated_ctx = json.dumps({
            **ctx,
            "status": "ended",
            "stream": {
                **stream_info,
                "ended_at": _utcnow().isoformat(),
            },
        })
        updated_session = ArtifactEntity.from_dict({
            **session.to_dict(),
            "context": updated_ctx,
        })
        arango.update_artifact(arango_db, updated_session)
        logger.info("Marked session %s as ended", artifact_id)


# ---------------------------------------------------------------------------
# Webhook endpoints (SRS → Mantle, internal Docker network only)
# ---------------------------------------------------------------------------

@router.post("/publish", status_code=status.HTTP_200_OK)
async def on_publish(
    request: Request,
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """SRS on_publish webhook — creates or resumes a stream session artifact.

    This endpoint is called by SRS from inside the Docker network.  It is
    not protected by the standard user-auth middleware.  The stream key in
    the payload serves as the credential.

    SRS expects a ``{"code": 0}`` response to allow the stream through.
    Any non-zero code or 4xx/5xx causes SRS to reject the publisher.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    stream_name = body.get("stream") or ""
    if not stream_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stream field")

    stream_key = _stream_key_without_app(stream_name)
    source_artifact_id, api_key = _parse_stream_key(stream_name)

    if not _SAFE_STREAM_RE.match(stream_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stream key contains invalid characters")

    async with _SESSION_LOCK:
        await _get_or_create_session(
            stream_key, stream_name, source_artifact_id, api_key, arango_db
        )

    return {"code": 0}


@router.post("/unpublish", status_code=status.HTTP_200_OK)
async def on_unpublish(
    request: Request,
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """SRS on_unpublish webhook — marks the session artifact as ended.

    Called when OBS stops streaming or disconnects.  The session artifact's
    context.status is set to "ended" and the ended_at timestamp is recorded.

    The stream gateway itself does not record or transcode.  If a recording
    is needed, configure a workspace event handler that reacts to the
    ``stream.session.ended`` event (handled by Astra or a custom handler).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    stream_name = body.get("stream") or ""
    stream_key = _stream_key_without_app(stream_name)

    async with _SESSION_LOCK:
        entry = _ACTIVE_SESSIONS.get(stream_key)
        if entry is not None:
            entry["last_unpublish"] = _utcnow()

            # Finalize after the idle window — allows SRS reconnect flap.
            async def _defer_finalize():
                await asyncio.sleep(_IDLE_WINDOW.total_seconds())
                async with _SESSION_LOCK:
                    e = _ACTIVE_SESSIONS.get(stream_key)
                    if e is not None and not _is_session_active(e, _utcnow()):
                        await _finalize_session(stream_key, arango_db)

            asyncio.create_task(_defer_finalize())

    return {"code": 0}


# ---------------------------------------------------------------------------
# Authenticated user endpoint
# ---------------------------------------------------------------------------

@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(
    source_artifact_id: Optional[str] = Query(None, description="Filter to a specific source artifact"),
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """List active stream sessions visible to the authenticated principal.

    If ``source_artifact_id`` is provided, the caller must have read access
    to that artifact and only its sessions are returned.  Without a filter
    all sessions where the caller has read access to the source are returned.
    """
    now = _utcnow()
    results = []

    async with _SESSION_LOCK:
        snapshot = list(_ACTIVE_SESSIONS.items())

    for _key, entry in snapshot:
        if not _is_session_active(entry, now):
            continue

        sid = entry.get("source_artifact_id", "")
        if source_artifact_id and sid != source_artifact_id:
            continue

        # Gate on read access to the source artifact.
        try:
            check_access(auth, sid, "read", arango_db)
        except HTTPException:
            continue

        results.append({
            "source_artifact_id": sid,
            "artifact_id": entry.get("artifact_id"),
            "workspace_id": entry.get("workspace_id"),
            "hls_url": entry.get("hls_url"),
            "status": "live",
        })

    return {"count": len(results), "sessions": results}
