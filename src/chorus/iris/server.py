"""
agience-server-iris — MCP Server
====================================
Routing & Communication: messaging, webhooks, connectivity, remote execution.

Iris connects agents, services, and external systems by managing routing,
transport, messaging, and remote execution. It is the communication
layer that ensures reliable connectivity between platform components and
the outside world.

Pipeline position: Networking & infrastructure.

Tools
-----
  send_email        — Send an email via the platform's Authorizer (Gmail API)
  send_message      — Send a message via a registered channel adapter
  get_messages      — Poll a channel for new messages since a cursor
  list_channels     — List registered channel adapters
  create_webhook    — Register an inbound webhook
  health_check      — Check health/availability of a service endpoint
  list_connections  — List registered service connections
  register_endpoint — Register a service endpoint for routing
  route_request     — Route a request to a registered endpoint
  exec_shell        — Execute a shell command in a sandboxed directory
  proxy_tool        — Proxy an MCP tool call through a registered endpoint
  fetch_url         — Fetch content from a URL and return it inline
  ask_human         — Ask a question to the human operator (async-capable)

Auth (Phase C)
--------------
  Service identity loaded once by the chorus host (chorus.private.pem).
  Persona signs its own kernel JWTs via _auth.sign_self_jwt() — no token
  exchange with Origin, no PLATFORM_INTERNAL_SECRET.

  AGIENCE_API_URI                ⬩ Base URI of the Mantle backend
  IRIS_AUTHORIZER_ARTIFACT_ID   ⬩ Artifact ID of the email Authorizer transform
  IRIS_AUTHORIZER_WORKSPACE_ID  ⬩ Workspace ID where the Authorizer artifact lives

Transport
---------
  MCP_TRANSPORT=streamable-http
  MCP_HOST=0.0.0.0
  MCP_PORT=8086
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import pathlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

log = logging.getLogger("agience-server-iris")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s - %(name)s - %(message)s")

AGIENCE_API_URI: str = os.getenv("AGIENCE_API_URI", "http://localhost:8081").rstrip("/")
IRIS_CLIENT_ID: str = "agience-server-iris"
IRIS_CWD: str = os.getenv("IRIS_CWD", "/workspace")
IRIS_AUTHORIZER_ARTIFACT_ID: str = os.getenv("IRIS_AUTHORIZER_ARTIFACT_ID", "")
IRIS_AUTHORIZER_WORKSPACE_ID: str = os.getenv("IRIS_AUTHORIZER_WORKSPACE_ID", "")

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "streamable-http")
MCP_HOST: str = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.getenv("MCP_PORT", "8086"))


# ---------------------------------------------------------------------------
# Shared authentication infrastructure (AgieceServerAuth)
# ---------------------------------------------------------------------------

from agience_server_auth import AgieceServerAuth as _AgieceServerAuth

_auth = _AgieceServerAuth(IRIS_CLIENT_ID, AGIENCE_API_URI)


async def _headers() -> dict[str, str]:
    """Headers with Iris's own kernel JWT (signed via the chorus service identity)."""
    return _auth.headers()


async def _user_headers() -> dict[str, str]:
    """Headers with the verified delegation JWT, or fall back to Iris's kernel JWT."""
    return _auth.user_headers()


def create_iris_app():
    """Return the Iris MCP ASGI app with verified middleware and startup hooks."""
    return _auth.create_app(mcp)


mcp = FastMCP(
    "agience-server-iris",
    instructions=(
        "You are Iris, the Agience routing and communication, transport, and routing server. "
        "Use Iris to send messages through channel adapters, manage webhooks, "
        "route requests between services, execute remote shell commands, and "
        "manage secure tunnels between hosts and the platform."
    ),
)

from artifact_helpers import register_types_manifest
register_types_manifest(mcp, "iris", __file__)


# ---------------------------------------------------------------------------
# Tool: send_email
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Send an email via the platform's configured email Authorizer (Gmail API). "
        "Obtains an OAuth access token through the Authorizer artifact, then sends "
        "via Gmail. Requires IRIS_AUTHORIZER_ARTIFACT_ID to be configured."
    )
)
async def send_email(
    to: str,
    subject: str,
    body_html: str,
) -> str:
    """Send an email using the platform Authorizer's OAuth credentials.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_html: HTML body of the email.
    """
    if not IRIS_AUTHORIZER_ARTIFACT_ID:
        return json.dumps({"error": "IRIS_AUTHORIZER_ARTIFACT_ID not configured on Iris"})

    # 1. Call the platform to get an access token via the Authorizer artifact.
    # User identity is carried by the delegation JWT at transport level.
    invoke_payload: dict = {}
    if IRIS_AUTHORIZER_WORKSPACE_ID:
        invoke_payload["workspace_id"] = IRIS_AUTHORIZER_WORKSPACE_ID

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{AGIENCE_API_URI}/artifacts/{IRIS_AUTHORIZER_ARTIFACT_ID}/op/invoke",
            headers=await _user_headers(),
            json=invoke_payload,
        )

    if resp.status_code != 200:
        return json.dumps({"error": f"Authorizer invoke failed: {resp.status_code} {resp.text[:300]}"})

    result = resp.json()
    # The Authorizer returns JSON with access_token and sender_address
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return json.dumps({"error": f"Unexpected authorizer response: {result[:200]}"})

    access_token = result.get("access_token")
    sender_address = result.get("sender_address", "")

    if not access_token:
        return json.dumps({"error": "No access_token returned from Authorizer", "detail": str(result)[:300]})

    # 2. Build MIME message
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["From"] = sender_address or "me"
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    # 3. Send via Gmail API
    async with httpx.AsyncClient(timeout=15) as client:
        gmail_resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"raw": raw_message},
        )

    if gmail_resp.status_code != 200:
        return json.dumps({"error": f"Gmail send failed: {gmail_resp.status_code} {gmail_resp.text[:300]}"})

    gmail_data = gmail_resp.json()
    return json.dumps({"status": "sent", "message_id": gmail_data.get("id"), "to": to})


# ---------------------------------------------------------------------------
# Tool: notify_inbound
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Notify the operator about an inbound artifact (contact form submission, "
        "webhook, newsletter subscribe, etc.). Fetches the artifact from Mantle, "
        "formats its content as an HTML email, and sends it via the platform's "
        "email Authorizer. Falls back to IRIS_NOTIFY_EMAIL env var if notify_to "
        "is omitted."
    )
)
async def notify_inbound(
    artifact_id: str,
    workspace_id: str,
    notify_to: str = "",
) -> str:
    """Operator notification for any inbound artifact.

    Args:
        artifact_id: ID of the artifact to read and summarize.
        workspace_id: Workspace that owns the artifact.
        notify_to: Recipient email address. Falls back to IRIS_NOTIFY_EMAIL.
    """
    recipient = notify_to.strip() or os.getenv("IRIS_NOTIFY_EMAIL", "").strip()
    if not recipient:
        return json.dumps({"error": "notify_to not specified and IRIS_NOTIFY_EMAIL not set"})

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{AGIENCE_API_URI}/artifacts/{artifact_id}",
            headers=await _user_headers(),
        )

    if resp.status_code != 200:
        return json.dumps({"error": f"Artifact fetch failed: {resp.status_code} {resp.text[:200]}"})

    artifact = resp.json()
    content_str = artifact.get("content", "")
    context_str = artifact.get("context", "{}")

    try:
        content = json.loads(content_str) if content_str else {}
    except (json.JSONDecodeError, TypeError):
        content = {"raw": content_str[:500]}

    try:
        ctx = json.loads(context_str) if context_str else {}
    except (json.JSONDecodeError, TypeError):
        ctx = {}

    source = ctx.get("source", "unknown")
    subject = f"[Agience] Inbound: {source} ({artifact_id[:8]})"

    rows = "".join(
        f"<tr><td style='padding:4px 8px;font-weight:bold;'>{k}</td>"
        f"<td style='padding:4px 8px;'>{v}</td></tr>"
        for k, v in (content.items() if isinstance(content, dict) else [("content", str(content))])
    )
    body_html = (
        "<html><body style='font-family:sans-serif;'>"
        f"<h2 style='color:#333;'>Inbound: {source}</h2>"
        "<table border='1' cellpadding='0' cellspacing='0' style='border-collapse:collapse;'>"
        f"{rows}"
        "</table>"
        f"<p style='color:#888;font-size:12px;margin-top:16px;'>"
        f"artifact_id: {artifact_id} | workspace: {workspace_id}"
        "</p></body></html>"
    )

    return await send_email(to=recipient, subject=subject, body_html=body_html)


# ---------------------------------------------------------------------------
# Tool: send_message
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Send a message via a registered channel adapter (Telegram, Slack, email). "
        "The message is routed through the platform's channel infrastructure."
    )
)
async def send_message(
    channel: str,
    text: str,
    recipient: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Args:
        channel: Channel adapter name (e.g. 'telegram', 'slack', 'email').
        text: Message body text.
        recipient: Target recipient (chat ID, channel name, email address).
        workspace_id: Optional workspace context.
    """
    if not workspace_id:
        return "Error: workspace_id is required for the MVP Iris send_message flow."

    payload = {
        "context": {
            "type": "message",
            "direction": "outbound",
            "channel": channel,
            "recipient": recipient,
            "iris": {"delivery": "recorded-only"},
        },
        "content": text,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts",
            headers=await _headers(),
            json=payload,
            timeout=30,
        )
    if resp.status_code >= 400:
        return f"Error: {resp.status_code} — {resp.text[:300]}"
    return json.dumps(resp.json(), indent=2)


# ---------------------------------------------------------------------------
# Tool: get_messages
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Poll a channel adapter for new messages since a given cursor. "
        "Returns message list sorted by time."
    )
)
async def get_messages(
    channel: str,
    cursor: Optional[str] = None,
    limit: int = 20,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Args:
        channel: Channel adapter name (e.g. 'telegram', 'slack').
        cursor: Opaque cursor from a previous call (omit for latest).
        limit: Max messages to return.
    """
    if not workspace_id:
        return "Error: workspace_id is required for the MVP Iris get_messages flow."

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts",
            headers=await _headers(),
            timeout=30,
        )
    if resp.status_code >= 400:
        return f"Error: {resp.status_code} — {resp.text[:300]}"

    cards = resp.json() or []
    filtered = []
    for card in cards:
        raw_context = card.get("context") or {}
        if isinstance(raw_context, str):
            try:
                raw_context = json.loads(raw_context)
            except Exception:
                raw_context = {}

        card_channel = raw_context.get("channel") or raw_context.get("inbound", {}).get("channel")
        if card_channel != channel:
            continue
        if raw_context.get("type") != "message" and "inbound" not in raw_context:
            continue
        filtered.append(card)

    if cursor:
        filtered = [card for card in filtered if str(card.get("id")) > cursor]

    return json.dumps(filtered[:limit], indent=2)


# ---------------------------------------------------------------------------
# Tool: list_channels
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List registered channel adapters for the current user. "
        "Returns available channels and their connection status."
    )
)
async def list_channels() -> str:
    channels = [
        {
            "name": "webhook",
            "direction": "inbound",
            "status": "ready",
            "delivery": "card-scoped inbound webhook",
        },
        {
            "name": "workspace-card",
            "direction": "outbound",
            "status": "ready",
            "delivery": "records outbound messages as workspace cards",
        },
    ]
    return json.dumps(channels, indent=2)


# ---------------------------------------------------------------------------
# Tool: create_webhook
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Register an inbound webhook and return its endpoint URL. "
        "External services can POST to this URL to trigger platform actions."
    )
)
async def create_webhook(
    workspace_id: str,
    source_artifact_id: str,
    label: Optional[str] = None,
) -> str:
    """
    Args:
        workspace_id: Workspace that owns the source card.
        source_artifact_id: Card ID that will own the inbound key.
        label: Optional human-readable label.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AGIENCE_API_URI}/workspaces/{workspace_id}/artifacts/{source_artifact_id}/inbound-key",
            headers=await _headers(),
            timeout=30,
        )
    if resp.status_code >= 400:
        return f"Error: {resp.status_code} — {resp.text[:300]}"

    payload = resp.json()
    inbound_key = payload.get("inbound_key")
    return json.dumps(
        {
            "label": label or source_artifact_id,
            "workspace_id": workspace_id,
            "source_artifact_id": source_artifact_id,
            "method": "POST",
            "url": f"{AGIENCE_API_URI}/inbound/messages",
            "headers": {"x-inbound-key": inbound_key},
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: health_check
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Check the health and availability of a service endpoint. "
        "Returns status, latency, and any error details."
    )
)
async def health_check(
    url: str,
    timeout: int = 10,
) -> str:
    """
    Args:
        url: URL of the service endpoint to check.
        timeout: Max seconds to wait for response.
    """
    return f"TODO: health_check not yet implemented. url={url}"


# ---------------------------------------------------------------------------
# Tool: list_connections
# ---------------------------------------------------------------------------

@mcp.tool(
    description="List registered service connections and their current status."
)
async def list_connections() -> str:
    return "TODO: list_connections not yet implemented."


# ---------------------------------------------------------------------------
# Tool: register_endpoint
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Register a service endpoint for routing. "
        "Registered endpoints can be targeted by route_request and proxy_tool."
    )
)
async def register_endpoint(
    name: str,
    url: str,
    protocol: str = "http",
) -> str:
    """
    Args:
        name: Logical name for the endpoint.
        url: Base URL of the service.
        protocol: Protocol type — 'http', 'grpc', 'websocket'.
    """
    return f"TODO: register_endpoint not yet implemented. name={name}, url={url}"


# ---------------------------------------------------------------------------
# Tool: route_request
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Route an HTTP request to a registered endpoint. "
        "Acts as a platform-aware proxy with auth injection."
    )
)
async def route_request(
    endpoint: str,
    method: str = "GET",
    path: str = "/",
    body: Optional[str] = None,
) -> str:
    """
    Args:
        endpoint: Name of a registered endpoint.
        method: HTTP method — GET, POST, PUT, DELETE.
        path: Request path appended to the endpoint base URL.
        body: Optional request body (JSON string).
    """
    return f"TODO: route_request not yet implemented. endpoint={endpoint}, path={path}"


# ---------------------------------------------------------------------------
# Tool: exec_shell
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Execute a shell command in a sandboxed working directory. "
        "Returns stdout/stderr. Use for build, test, and lint tasks "
        "on remote or local compute environments."
    )
)
async def exec_shell(
    command: str,
    working_directory: Optional[str] = None,
    timeout: int = 60,
) -> str:
    """
    Args:
        command: Shell command to run (e.g. 'pytest tests/').
        working_directory: Absolute path inside the sandbox.
        timeout: Max seconds before kill.
    """
    cwd = working_directory or IRIS_CWD
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        rc = proc.returncode
        return f"exitcode={rc}\n{output}"
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tool: proxy_tool
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Proxy an MCP tool call through a registered endpoint. "
        "Forwards the tool invocation to a remote MCP server and returns the result."
    )
)
async def proxy_tool(
    endpoint: str,
    tool_name: str,
    arguments: Optional[str] = None,
) -> str:
    """
    Args:
        endpoint: Name of a registered endpoint.
        tool_name: Name of the MCP tool to invoke on the remote server.
        arguments: JSON string of tool arguments.
    """
    return f"TODO: proxy_tool not yet implemented. endpoint={endpoint}, tool={tool_name}"


# ---------------------------------------------------------------------------
# Tool: fetch_url
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Fetch content from a URL and return it inline. "
        "Useful for reading web pages, API responses, or any HTTP-accessible resource. "
        "Does NOT create an artifact — use create_artifact separately to persist."
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def fetch_url(
    url: str,
    query: Optional[str] = None,
    format: Optional[str] = "text",
    timeout: int = 30,
    max_length: int = 100000,
) -> str:
    """
    Args:
        url: The URL to fetch.
        query: Optional — extract only content relevant to this query (requires LLM).
        format: Response format — 'text' (default), 'markdown', or 'html'.
        timeout: Max seconds to wait for response.
        max_length: Max characters to return (default 100k, truncates with notice).
    """
    import re

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Agience/1.0 (Iris)"})
    except httpx.TimeoutException:
        return json.dumps({"error": f"Request timed out after {timeout}s", "url": url})
    except httpx.RequestError as exc:
        return json.dumps({"error": f"Request failed: {exc}", "url": url})

    if resp.status_code >= 400:
        return json.dumps({"error": f"HTTP {resp.status_code}", "url": url, "body": resp.text[:500]})

    content_type = resp.headers.get("content-type", "")
    raw_text = resp.text

    # Strip HTML tags for text/markdown output
    if format in ("text", "markdown") and "html" in content_type:
        # Basic tag stripping — good enough for inline reading
        raw_text = re.sub(r"<script[^>]*>.*?</script>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
        raw_text = re.sub(r"<style[^>]*>.*?</style>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
        raw_text = re.sub(r"<[^>]+>", " ", raw_text)
        raw_text = re.sub(r"\s+", " ", raw_text).strip()
    elif format == "html":
        pass  # Return raw HTML

    # Truncate if needed
    truncated = False
    if len(raw_text) > max_length:
        raw_text = raw_text[:max_length]
        truncated = True

    result: dict = {
        "url": url,
        "status": resp.status_code,
        "content_type": content_type,
        "length": len(raw_text),
        "content": raw_text,
    }
    if truncated:
        result["truncated"] = True
        result["notice"] = f"Content truncated to {max_length} characters."

    # TODO(agents-invoke-removal): the "extract" agent is a legacy backend
    # plugin that does not exist and has no server mapping. Query-driven
    # extraction via fetch_url is disabled pending redesign — callers should
    # use Verso's invoke_llm directly with a properly configured connection
    # artifact.
    if query and raw_text:
        log.info("fetch_url: query parameter ignored (extract agent not available)")

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: ask_human
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Ask a question to the human operator. Creates a pending question artifact "
        "in the workspace and attempts delivery through available channels: "
        "browser relay (if connected), configured notification channel, or "
        "async artifact (human answers when they return). "
        "Use urgency='blocking' to wait for a response, 'deferred' to continue working."
    ),
)
async def ask_human(
    workspace_id: str,
    question: str,
    options: Optional[list[str]] = None,
    urgency: str = "deferred",
    timeout_seconds: int = 120,
) -> str:
    """
    Args:
        workspace_id: Workspace where the question artifact will be created.
        question: The question text to present to the human.
        options: Optional list of structured answer choices.
        urgency: 'blocking' to wait for an answer, 'deferred' to return immediately.
        timeout_seconds: Max seconds to wait when urgency is 'blocking'.
    """
    # 1. Create a pending-question artifact in the workspace
    question_context = {
        "type": "pending_question",
        "question": question,
        "status": "pending",
    }
    if options:
        question_context["options"] = options

    headers = await _user_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        create_resp = await client.post(
            f"{AGIENCE_API_URI}/artifacts",
            headers=headers,
            json={
                "workspace_id": workspace_id,
                "content": question,
                "context": json.dumps(question_context),
            },
        )

    if create_resp.status_code >= 400:
        return json.dumps({"error": f"Failed to create question artifact: {create_resp.status_code}"})

    artifact = create_resp.json().get("artifact", create_resp.json())
    artifact_id = artifact.get("id")

    # 2. Check relay presence — is the human connected via browser?
    relay_connected = False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            relay_resp = await client.get(
                f"{AGIENCE_API_URI}/mcp",
                headers=headers,
                params={"tool": "relay_status"},
            )
            if relay_resp.status_code == 200:
                relay_data = relay_resp.json()
                relay_connected = relay_data.get("connected", False)
    except Exception:
        pass  # Relay check is best-effort

    # 3. Deliver the question
    delivery_method = "artifact_only"

    if relay_connected:
        # Human is online — the artifact creation event will notify them via
        # the WebSocket event stream. The question card appears in their workspace.
        delivery_method = "relay_event"

    # 4. For blocking mode, poll for an answer
    if urgency == "blocking" and relay_connected:
        import time
        deadline = time.time() + timeout_seconds
        poll_interval = 3  # seconds

        while time.time() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    check_resp = await client.get(
                        f"{AGIENCE_API_URI}/artifacts/{workspace_id}/artifacts/{artifact_id}",
                        headers=headers,
                    )
                if check_resp.status_code == 200:
                    updated = check_resp.json()
                    ctx = updated.get("context", {})
                    if isinstance(ctx, str):
                        ctx = json.loads(ctx)
                    if ctx.get("status") == "answered":
                        return json.dumps({
                            "status": "answered",
                            "answer": ctx.get("answer"),
                            "artifact_id": artifact_id,
                            "delivery_method": delivery_method,
                        })
            except Exception:
                pass

        return json.dumps({
            "status": "timeout",
            "artifact_id": artifact_id,
            "delivery_method": delivery_method,
            "message": f"No answer received within {timeout_seconds}s. Question remains pending.",
        })

    return json.dumps({
        "status": "pending",
        "artifact_id": artifact_id,
        "delivery_method": delivery_method,
        "message": "Question created. Human will see it when they access the workspace.",
    })


# ---------------------------------------------------------------------------
# UI Resources
# ---------------------------------------------------------------------------

@mcp.resource("ui://iris/vnd.agience.host.html")
async def host_viewer_html() -> str:
    """Serve the viewer HTML for vnd.agience.host+json."""
    view_path = pathlib.Path(__file__).parent / "ui" / "application" / "vnd.agience.host+json" / "view.html"
    return view_path.read_text(encoding="utf-8")


@mcp.resource("ui://iris/vnd.agience.mcp-client.html")
async def mcp_client_viewer_html() -> str:
    """Serve the viewer HTML for vnd.agience.mcp-client+json."""
    view_path = pathlib.Path(__file__).parent / "ui" / "application" / "vnd.agience.mcp-client+json" / "view.html"
    return view_path.read_text(encoding="utf-8")


@mcp.resource("ui://iris/vnd.agience.mcp-server.html")
async def mcp_server_viewer_html() -> str:
    """Serve the viewer HTML for vnd.agience.mcp-server+json."""
    view_path = pathlib.Path(__file__).parent / "ui" / "application" / "vnd.agience.mcp-server+json" / "view.html"
    return view_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Standard server interface (used by _host and standalone)
# ---------------------------------------------------------------------------

def create_server_app():
    """Return the Iris ASGI app with verified middleware and startup hooks."""
    return create_iris_app()


async def server_startup() -> None:
    """Run Iris startup tasks. Trust map is on disk in Phase C; nothing to fetch."""
    await _auth.startup()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting agience-server-iris — transport=%s port=%s", MCP_TRANSPORT, MCP_PORT)
    if MCP_TRANSPORT == "streamable-http":
        import uvicorn
        uvicorn.run(create_server_app(), host=MCP_HOST, port=MCP_PORT)
    else:
        mcp.run()
