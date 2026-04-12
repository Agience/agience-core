"""Astra stream lifecycle routes — SRS webhook handlers.

These FastAPI routes run on the Astra MCP server (not Core backend).
All platform operations are performed via HTTP calls to the Core API
using ``PLATFORM_INTERNAL_SECRET`` + client_credentials for authentication.

Endpoints:
  POST /stream/publish      — SRS on_publish webhook
  POST /stream/unpublish    — SRS on_unpublish webhook
  GET  /stream/session      — Resolve stream key to active session
  GET  /stream/sessions     — List active sessions (optional source filter)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger("astra.stream_routes")

AGIENCE_API_URI: str = os.getenv("AGIENCE_API_URI", "http://localhost:8081").rstrip("/")
PLATFORM_INTERNAL_SECRET: str | None = os.getenv("PLATFORM_INTERNAL_SECRET")
STREAM_ROUTES_CLIENT_ID: str = "agience-server-astra"
STREAM_BASE_URL: str = os.getenv("STREAM_BASE_URL", "http://stream:1985/live").rstrip("/")

router = APIRouter(prefix="/stream", tags=["Stream"])

# ---------------------------------------------------------------------------
# In-memory session state (guarded by _SESSION_LOCK)
# ---------------------------------------------------------------------------

_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_LOCK = asyncio.Lock()
_IDLE_WINDOW = timedelta(seconds=10)

# ---------------------------------------------------------------------------
# Platform auth — client_credentials token exchange
# ---------------------------------------------------------------------------

_token_state: dict = {"access_token": None, "expires_at": 0.0}
_token_lock = asyncio.Lock()


async def _exchange_token() -> str | None:
    """Exchange kernel credentials for a platform JWT; refreshes 60 s before expiry."""
    if not PLATFORM_INTERNAL_SECRET:
        return None

    import time

    async with _token_lock:
        if _token_state["access_token"] and time.time() < _token_state["expires_at"] - 60:
            return _token_state["access_token"]

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{AGIENCE_API_URI}/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": STREAM_ROUTES_CLIENT_ID,
                    "client_secret": PLATFORM_INTERNAL_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            body = resp.json()

        token = body["access_token"]
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        _token_state["access_token"] = token
        _token_state["expires_at"] = float(payload.get("exp", time.time() + 43200))
        return token


async def _headers(bearer: str | None = None) -> dict[str, str]:
    """Build request headers. Uses the provided bearer token directly, or exchanges
    PLATFORM_INTERNAL_SECRET for a server JWT when no bearer is given."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    token = bearer if bearer is not None else await _exchange_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# Validate stream key characters — alphanumeric, hyphens, underscores, colons.
_SAFE_STREAM_RE = re.compile(r"^[a-zA-Z0-9\-_:]+$")


def _is_session_active(entry: Dict[str, Any], now: datetime) -> bool:
    """Determine whether a session should be treated as active.

    A session is active when:
    - it has never been unpublished, OR
    - it was republished after the last unpublish, OR
    - it was unpublished very recently (grace window) to avoid flapping.
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Stream key parsing
# ---------------------------------------------------------------------------


def _parse_stream_key(stream_name: str) -> tuple[str, str]:
    """Parse SRS stream key.

    SRS webhooks include the app name prefix, so the format is:
    ``{app}/{source_artifact_id}:{api_key}`` (e.g. ``live/abc-123:agc_xyz``).

    We strip the app prefix and return ``(source_artifact_id, api_key)``.
    """
    val = (stream_name or "").strip()
    if not val:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stream key")

    # Strip SRS app name prefix (e.g. "live/") if present.
    if "/" in val:
        _app_name, _, remainder = val.partition("/")
        if ":" in remainder:
            val = remainder

    if ":" not in val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stream key (expected '{source_artifact_id}:{token}')",
        )
    source_artifact_id, token = val.split(":", 1)
    source_artifact_id = source_artifact_id.strip()
    token = token.strip()
    if not source_artifact_id or not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stream key (expected '{source_artifact_id}:{token}')",
        )
    return source_artifact_id, token


def _stream_key_without_app(stream_name: str) -> str:
    """Return the stream key with the SRS app prefix stripped.

    Used for session dict keys and HLS path construction so the app
    prefix (``live/``) doesn't leak into artifact IDs or file paths.
    """
    val = (stream_name or "").strip()
    if "/" in val:
        _app_name, _, remainder = val.partition("/")
        if ":" in remainder:
            return remainder
    return val


# ---------------------------------------------------------------------------
# Core API helpers
# ---------------------------------------------------------------------------

async def _lookup_artifact_global(artifact_id: str) -> dict:
    """Look up a workspace artifact by ID using the global batch endpoint."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{AGIENCE_API_URI}/workspaces/artifacts/batch",
            headers=await _headers(),
            json={"artifact_ids": [artifact_id]},
        )
    if resp.status_code != 200:
        logger.error("Core batch lookup failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Core API error: {resp.status_code}")
    items = resp.json()
    if not items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source artifact not found")
    return items[0]


async def _create_workspace_artifact(workspace_id: str, context: dict, content: str = "") -> dict:
    """Create a new artifact in a workspace via Core API."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts",
            headers=await _headers(),
            json={"context": context, "content": content},
        )
    if resp.status_code not in (200, 201):
        logger.error("Failed to create artifact: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Failed to create session artifact")
    return resp.json()


async def _get_artifact(workspace_id: str, artifact_id: str) -> dict:
    """Fetch a single artifact from a workspace."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{artifact_id}",
            headers=await _headers(),
        )
    if resp.status_code != 200:
        logger.warning("Failed to fetch artifact %s: %s", artifact_id, resp.status_code)
        return {}
    return resp.json()


async def _update_artifact(workspace_id: str, artifact_id: str, context: dict | None = None, content: str | None = None) -> dict:
    """Update an artifact's context and/or content via Core API.

    Note: The Core PATCH endpoint **replaces** the context entirely.
    Callers must pass the full merged context, not a partial update.
    """
    body: dict[str, Any] = {}
    if context is not None:
        body["context"] = context
    if content is not None:
        body["content"] = content
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{artifact_id}",
            headers=await _headers(),
            json=body,
        )
    if resp.status_code != 200:
        logger.warning("Failed to update artifact %s: %s", artifact_id, resp.text[:300])
    return resp.json() if resp.status_code == 200 else {}


async def _upload_file_to_artifact(workspace_id: str, artifact_id: str, file_path: str, content_type: str = "video/mp4") -> bool:
    """Upload a local file to an artifact via Core's presigned upload flow."""
    # Step 1: Initiate upload
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{artifact_id}/upload-initiate",
                headers=await _headers(),
                json={"content_type": content_type},
            )
    except httpx.RequestError as exc:
        logger.error("Upload initiate request failed: %s", exc)
        return False
    if resp.status_code not in (200, 201):
        logger.error("Upload initiate failed: %s %s", resp.status_code, resp.text[:300])
        return False
    try:
        upload_data = resp.json()
    except Exception:
        logger.error("Upload initiate returned invalid JSON")
        return False
    presigned_url = upload_data.get("url")
    if not presigned_url:
        logger.error("No presigned URL in upload-initiate response")
        return False

    # Step 2: Upload file to presigned URL
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.put(
            presigned_url,
            content=file_bytes,
            headers={"Content-Type": content_type},
        )
    if resp.status_code not in (200, 201, 204):
        logger.error("S3 upload failed: %s", resp.status_code)
        return False

    # Step 3: Mark upload complete
    file_size = len(file_bytes)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{artifact_id}/upload-status",
            headers=await _headers(),
            json={"status": "complete", "size": file_size},
        )
    if resp.status_code != 200:
        logger.warning("Upload status patch failed: %s %s", resp.status_code, resp.text[:300])
        return False

    return True


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

async def _get_or_create_session(
    stream: str, source_artifact_id: str, api_key: str,
) -> Dict[str, Any]:
    """Return the in-memory session entry for *stream*, creating if needed.

    Must be called under ``_SESSION_LOCK``.

    On creation:
      1. Look up the source artifact via Core API (global batch).
      2. Validate the API key by calling Core with it as Bearer.
      3. Read target_content_type from the source artifact context.
      4. Create a session artifact of the configured content type.
      5. Append the session ID to the source artifact's sessions[] list.
    """
    entry = _ACTIVE_SESSIONS.get(stream)
    now = _utcnow()

    if entry is not None:
        last_unpublish: Optional[datetime] = entry.get("last_unpublish")
        if last_unpublish is None or (now - last_unpublish) <= _IDLE_WINDOW:
            entry["last_publish"] = now
            entry["last_unpublish"] = None
            logger.debug("Reusing session for stream %s", stream)
            return entry

    # Look up the source artifact.
    source = await _lookup_artifact_global(source_artifact_id)
    workspace_id = source.get("workspace_id")
    owner_id = source.get("owner_id") or source.get("user_id")
    if not workspace_id or not owner_id:
        logger.error(
            "Source artifact %s missing required fields: workspace_id=%s owner_id=%s",
            source_artifact_id, workspace_id, owner_id,
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source artifact incomplete")

    # Parse source artifact context.
    source_ctx: dict = {}
    raw_ctx = source.get("context")
    if isinstance(raw_ctx, str):
        try:
            source_ctx = json.loads(raw_ctx)
        except Exception:
            source_ctx = {}
    elif isinstance(raw_ctx, dict):
        source_ctx = raw_ctx

    stream_cfg: dict = source_ctx.get("stream") or {}

    # Validate the API key: must be agc_* format and resolve against Core.
    if not api_key.startswith("agc_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid stream key")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            verify_resp = await client.get(
                f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{source_artifact_id}",
                headers=_headers(bearer=api_key),
            )
    except httpx.RequestError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Core API unreachable")
    if verify_resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid stream key")

    target_content_type: str = stream_cfg.get("target_content_type") or "video/mp4"

    # Create session artifact.
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    session_context = {
        "content_type": target_content_type,
        "title": f"Stream \u2014 {now_str}",
        "type": "stream-session",
        "status": "live",
        "source_artifact_id": source_artifact_id,
    }
    session = await _create_workspace_artifact(workspace_id, session_context, content="")
    session_artifact_id = session.get("id")

    logger.info(
        "Created session artifact %s for source %s in workspace %s",
        session_artifact_id, source_artifact_id, workspace_id,
    )

    # Append session ID to source artifact's sessions[] list.
    sessions_list = list(stream_cfg.get("sessions") or [])
    sessions_list.append(session_artifact_id)
    updated_stream_cfg = {**stream_cfg, "sessions": sessions_list}
    updated_source_ctx = {**source_ctx, "stream": updated_stream_cfg}
    try:
        await _update_artifact(workspace_id, source_artifact_id, context=updated_source_ctx)
    except Exception as exc:
        logger.warning("Failed to append session to source %s: %s", source_artifact_id, exc)

    entry = {
        "workspace_id": workspace_id,
        "source_artifact_id": source_artifact_id,
        "artifact_id": session_artifact_id,
        "owner_id": owner_id,
        "session_context": session_context,
        "last_publish": now,
        "last_unpublish": None,
    }
    _ACTIVE_SESSIONS[stream] = entry
    return entry


# ---------------------------------------------------------------------------
# HLS -> MP4 finalization
# ---------------------------------------------------------------------------

async def _finalize_recording(stream: str, entry: Dict[str, Any]) -> None:
    """Mux HLS segments into MP4 and upload to S3 via Core presigned flow.

    HLS files live on the shared ``/var/stream`` volume mounted from the SRS
    container.  The ``servers`` container must also mount this volume.
    """
    workspace_id = entry["workspace_id"]
    artifact_id = entry["artifact_id"]

    # Validate stream name to prevent path traversal.
    if not _SAFE_STREAM_RE.match(stream):
        logger.error("Refusing to finalize stream with unsafe name: %s", stream[:60])
        return

    # SRS writes HLS to /var/stream/live/{stream_name}/.
    hls_path = f"/var/stream/live/{stream}/index.m3u8"

    # Check if HLS segments exist.
    if not os.path.isfile(hls_path):
        logger.info("No HLS segments found at %s — skipping MP4 finalization", hls_path)
        return

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        mp4_path = tmp.name

    try:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", hls_path,
            "-c", "copy",
            "-movflags", "+faststart",
            mp4_path,
        ]
        logger.info("Running ffmpeg for session %s", artifact_id)
        proc = await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            capture_output=True,
            timeout=300,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace")
            logger.error("ffmpeg failed (rc=%d): %s", proc.returncode, stderr[:1000])
            return

        success = await _upload_file_to_artifact(workspace_id, artifact_id, mp4_path)
        if success:
            logger.info("MP4 uploaded for session %s", artifact_id)
        else:
            logger.error("MP4 upload failed for session %s", artifact_id)
    except Exception as exc:
        logger.error("Finalization failed for session %s: %s", artifact_id, exc)
    finally:
        try:
            os.unlink(mp4_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@router.post("/publish", status_code=status.HTTP_200_OK)
async def on_publish(request: Request):
    """SRS on_publish webhook — creates or resumes a stream session."""
    body = await request.json()
    raw_stream = str(body.get("stream") or "")
    source_artifact_id, token = _parse_stream_key(raw_stream)

    # Use the stripped key (without app prefix) for session tracking.
    stream = _stream_key_without_app(raw_stream)

    async with _SESSION_LOCK:
        session = await _get_or_create_session(stream, source_artifact_id, token)

    return {
        "code": 0,
        "status": "ok",
        "workspace_id": session["workspace_id"],
        "source_artifact_id": session["source_artifact_id"],
        "artifact_id": session["artifact_id"],
    }


@router.post("/unpublish", status_code=status.HTTP_200_OK)
async def on_unpublish(request: Request):
    """SRS on_unpublish webhook — marks session ended, finalizes recording."""
    body = await request.json()
    raw_stream = str(body.get("stream") or "")
    stream = _stream_key_without_app(raw_stream)

    async with _SESSION_LOCK:
        entry = _ACTIVE_SESSIONS.get(stream)
        if not entry:
            return {"code": 0, "status": "ignored"}

        entry["last_unpublish"] = _utcnow()

        workspace_id = entry["workspace_id"]
        artifact_id = entry["artifact_id"]

        # Fetch the current session artifact context so we can merge the
        # status update instead of replacing the entire context.
        try:
            current = await _get_artifact(workspace_id, artifact_id)
            current_ctx = current.get("context", {})
            if isinstance(current_ctx, str):
                current_ctx = json.loads(current_ctx)
            merged_ctx = {**current_ctx, "status": "ended"}
            await _update_artifact(workspace_id, artifact_id, context=merged_ctx)
        except Exception as exc:
            logger.error("Failed to update session %s status: %s", artifact_id, exc)

        # Remove from active sessions before starting finalization.
        _ACTIVE_SESSIONS.pop(stream, None)

    # Finalize HLS -> MP4 and upload (runs outside the lock).
    asyncio.create_task(_finalize_recording(stream, entry))

    return {"code": 0, "status": "ok"}


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

@router.get("/session", status_code=status.HTTP_200_OK)
def get_session(stream: str):
    """Return the active session mapping for a given stream key."""
    entry = _ACTIVE_SESSIONS.get(stream)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active session for stream")

    now = _utcnow()
    if not _is_session_active(entry, now):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active session for stream")

    return {
        "workspace_id": entry["workspace_id"],
        "source_artifact_id": entry.get("source_artifact_id"),
        "artifact_id": entry["artifact_id"],
    }


@router.get("/sessions", status_code=status.HTTP_200_OK)
def list_sessions(source_artifact_id: Optional[str] = None):
    """List active stream sessions.

    If ``source_artifact_id`` is provided, returns sessions for that specific
    source (used by the stream viewer to check live status).
    """
    now = _utcnow()
    sessions = []
    for _stream_key, entry in _ACTIVE_SESSIONS.items():
        if not _is_session_active(entry, now):
            continue
        if source_artifact_id is not None:
            if entry.get("source_artifact_id") != source_artifact_id:
                continue
        sessions.append({
            "workspace_id": entry.get("workspace_id"),
            "source_artifact_id": entry.get("source_artifact_id"),
            "artifact_id": entry.get("artifact_id"),
            "status": "live",
        })

    return {"count": len(sessions), "sessions": sessions}
