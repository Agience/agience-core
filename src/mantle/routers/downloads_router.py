"""Static download redirects.

The only surviving piece of the old relay router (Step G consolidation):
a 302 redirect from `/relay/download?platform=…` to the corresponding
desktop-relay installer binary on the configured CDN base URL.

The relay WebSocket and session management moved to Chorus
(`/relay/v1/connect` on port 8082) — this router only owns the
installer-download redirect, which has no service dependencies.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from kernel import config


router = APIRouter(tags=["Downloads"])

_PLATFORM_SUFFIXES = {
    "windows": ("agience-relay-windows", ".exe"),
    "macos":   ("agience-relay-macos",   ".dmg"),
    "linux":   ("agience-relay-linux",   ".AppImage"),
}


@router.get("/relay/download", status_code=status.HTTP_302_FOUND)
def relay_download(platform: str = Query(..., description="Target platform: windows, macos, or linux")):
    """Redirect to the Desktop Host Relay installer for the requested platform."""
    key = platform.lower().strip()
    entry = _PLATFORM_SUFFIXES.get(key)
    if not entry:
        raise HTTPException(status_code=400, detail=f"Unknown platform {platform!r}. Use: windows, macos, linux")
    name, ext = entry
    url = f"{config.DESKTOP_RELAY_DOWNLOAD_BASE_URL}/{name}{ext}"
    return RedirectResponse(url=url, status_code=302)
