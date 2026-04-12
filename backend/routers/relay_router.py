from __future__ import annotations

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import RedirectResponse

from core import config
from services import auth_service
from services import desktop_host_relay_service
from services.dependencies import get_auth, AuthContext, is_api_key_jwt_payload


router = APIRouter(prefix="/relay", tags=["Relay"])

_PLATFORM_SUFFIXES = {
    "windows": ("agience-relay-windows", ".exe"),
    "macos": ("agience-relay-macos", ".dmg"),
    "linux": ("agience-relay-linux", ".AppImage"),
}


@router.get("/download", status_code=status.HTTP_302_FOUND, include_in_schema=True)
def relay_download(platform: str = Query(..., description="Target platform: windows, macos, or linux")):
    """Redirect to the Desktop Host Relay installer for the requested platform."""
    key = platform.lower().strip()
    entry = _PLATFORM_SUFFIXES.get(key)
    if not entry:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown platform {platform!r}. Use: windows, macos, linux")
    name, ext = entry
    url = f"{config.DESKTOP_RELAY_DOWNLOAD_BASE_URL}/{name}{ext}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/sessions/me", status_code=status.HTTP_200_OK)
def list_my_relay_sessions(auth: AuthContext = Depends(get_auth)):
    return {"sessions": desktop_host_relay_service.relay_manager.list_sessions_for_user(auth.user_id)}


@router.websocket("/v1/connect")
async def relay_connect(websocket: WebSocket):
    authorization = websocket.headers.get("authorization") or ""
    if not authorization.startswith("Bearer "):
        await websocket.close(code=4401, reason="Missing bearer token")
        return

    token = authorization.replace("Bearer ", "", 1)
    payload = auth_service.verify_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=4401, reason="Invalid bearer token")
        return
    if is_api_key_jwt_payload(payload):
        await websocket.close(code=4403, reason="API key token not valid for this endpoint")
        return

    await websocket.accept()
    session = await desktop_host_relay_service.relay_manager.connect_session(
        websocket,
        user_id=str(payload["sub"]),
        client_id=str(payload.get("client_id")) if payload.get("client_id") is not None else None,
    )
    await websocket.send_json(desktop_host_relay_service.relay_manager.server_hello(session))

    try:
        while True:
            message = await websocket.receive_json()
            response = await desktop_host_relay_service.relay_manager.handle_message(session.session_id, message)
            if response is not None:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        await desktop_host_relay_service.relay_manager.disconnect_session(session.session_id)