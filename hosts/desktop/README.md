# Agience Desktop Relay Host

Status: **Draft**
Date: 2026-03-07

This package is the start of the desktop relay runtime described in `.dev/features/desktop-host-relay.md`.

Current intent:

- run a thin local Agience host without Postgres, ArangoDB, or OpenSearch
- expose the first-party MCP persona servers from the source tree
- reserve a future controller-facing runtime role for the full platform control plane

Mode naming:

- `host`: the desktop relay companion runtime
- `authority`: the future controller/runtime with the full control plane and infrastructure

`authority` was chosen over `domain` because this split is about operational control, not tenant or namespace boundaries.

What exists now:

- runtime configuration and mode parsing
- a source-tree MCP host app that mounts the persona servers directly from `servers/`
- a desktop relay host entrypoint for local execution
- a `desktop-host` MCP surface with safe read-only filesystem tools
- a preapproved local server supervisor for manual lifecycle management
- an optional outbound relay client loop for authority connection

What does not exist yet:

- browser relay parity
- authority runtime bootstrapping
- durable local MCP process pooling (current local MCP proxy is one-shot per request)

## Current test status

The desktop relay host is ready for local end-to-end testing against a running Agience backend authority.

What has been validated in-repo:

- backend relay session registration and tool round-trip tests pass
- desktop host config and relay runtime tests pass
- backend startup includes the relay router successfully

What is still considered MVP-grade rather than finished product:

- desktop authentication bootstrap is manual
- local MCP proxying is request-by-request rather than pooled
- browser relay has not been built yet

## Usage

From this directory:

```bash
python -m agience_relay_host.main --mode host --bind-host 127.0.0.1 --bind-port 8082
```

Optional config file:

```bash
python -m agience_relay_host.main --config ./config.example.json
```

Relevant environment variables:

- `AGIENCE_RELAY_MODE=host|authority`
- `AGIENCE_AUTHORITY_URL=https://agience.example.com`
- `AGIENCE_RELAY_BIND_HOST=127.0.0.1`
- `AGIENCE_RELAY_BIND_PORT=8082`
- `AGIENCE_RELAY_ENABLED_PERSONAS=aria,sage,atlas,nexus,astra,verso,seraph,ophan`
- `AGIENCE_RELAY_DISPLAY_NAME=My Desktop Host`
- `AGIENCE_RELAY_DEVICE_ID=device-123`
- `AGIENCE_RELAY_ALLOWED_ROOTS=C:/work,C:/Users/john/Documents`
- `AGIENCE_RELAY_SERVICE_DEFINITIONS_DIR=./service-definitions`
- `AGIENCE_RELAY_ACCESS_TOKEN=<agience access token>`
- `AGIENCE_RELAY_CLIENT_VERSION=0.1.0`

Persona servers still depend on their normal environment, especially `AGIENCE_API_URI` and `PLATFORM_INTERNAL_SECRET`.

If `authority_url` and `access_token` are configured, the desktop host will also attempt to maintain an outbound relay connection to `/relay/v1/connect`.

## Local install

From the repository root:

```powershell
Set-Location distributions/relay/desktop
python -m pip install -e .
```

This installs the desktop relay package in editable mode so local code changes are picked up immediately.

## End-to-end local connection

### 1. Start the backend authority

From the repository root:

```powershell
Set-Location backend
python main.py
```

Expected result:

- backend listens on `http://localhost:8081`
- startup completes without relay-related errors

### 2. Obtain a bearer token

Use a real Agience access token if you already have one from local sign-in.

For local development, you can mint a JWT directly:

```powershell
Set-Location backend
python -c "from services.auth_service import create_jwt_token; print(create_jwt_token({'sub':'YOUR_USER_ID','client_id':'desktop-host'}))"
```

Notes:

- replace `YOUR_USER_ID` with the Agience user id you want the desktop host session to represent
- `client_id` should stay `desktop-host`
- this token is sufficient for relay session setup and backend-side testing

### 3. Configure the desktop host

Edit `config.example.json` or copy it to a local config file and set:

- `mode`: `host`
- `authority_url`: `http://localhost:8081`
- `access_token`: the token from the previous step
- `allowed_roots`: the local directories you want desktop filesystem tools to access
- `enabled_personas`: whichever persona servers you want exposed locally

Minimal example:

```json
{
	"mode": "host",
	"authority_url": "http://localhost:8081",
	"access_token": "<paste token here>",
	"bind_host": "127.0.0.1",
	"bind_port": 8082,
	"allowed_roots": [
		"C:/Users/john/Documents"
	],
	"service_definitions_dir": "./service-definitions",
	"enabled_personas": ["aria", "nexus"],
	"log_level": "INFO"
}
```

### 4. Start the desktop host

From `distributions/relay/desktop`:

```powershell
python -m agience_relay_host.main --config .\config.example.json
```

Expected result:

- desktop host starts on `http://127.0.0.1:8082`
- if `authority_url` and `access_token` are valid, it attempts relay connection automatically

### 5. Verify desktop-side status

In a separate terminal:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8082/relay/status"
```

Expected result after successful handshake:

- `configured: true`
- `connected: true`
- `session_id` populated

### 6. Verify authority-side session registration

In PowerShell:

```powershell
$headers = @{ Authorization = "Bearer <paste token here>" }
Invoke-RestMethod -Uri "http://localhost:8081/relay/sessions/me" -Headers $headers
```

Expected result:

- one active session for the current user
- `display_name`, `device_id`, and `capabilities_manifest` present after `client_hello`

### 6a. Optional one-command smoke test

Once the backend and desktop host are both running, you can verify both sides with a single command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\smoke-test.ps1 -Token "<paste token here>"
```

Optional parameters:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\smoke-test.ps1 `
	-Token "<paste token here>" `
	-AuthorityUrl "http://localhost:8081" `
	-DesktopHostUrl "http://127.0.0.1:8082" `
	-TimeoutSeconds 30
```

The script checks:

- desktop `/relay/status`
- authority `/relay/sessions/me`
- required built-in desktop-host tools
- absence of invalid `local-mcp:local-mcp:*` ids

### 7. Optional focused regression checks

Backend relay tests:

```powershell
Set-Location backend
pytest tests/test_desktop_host_relay_service.py tests/test_relay_router.py
```

Desktop host tests:

```powershell
Set-Location distributions/relay/desktop
pytest tests/test_config.py
```

## Optional local MCP server definitions

If you want the desktop host to advertise additional local MCP servers, add JSON definitions under `service-definitions/`.

Example:

```json
{
	"server_id": "sample",
	"label": "Sample Local Server",
	"command": ["python", "server.py"],
	"cwd": "C:/path/to/server"
}
```

Behavior:

- the desktop host advertises this server to the authority as `local-mcp:sample`
- backend routing already understands the `local-mcp:` namespace
- the current implementation proxies each call as a one-shot subprocess request

## Built-in desktop-host tools

The host runtime now mounts a dedicated MCP server at `/desktop-host/mcp` with:

- `host_status`
- `fs_list_dir`
- `fs_read_text`
- `mcp_servers_list_local`
- `mcp_servers_start_local`
- `mcp_servers_stop_local`

Filesystem tools are restricted to configured allowlisted roots.

Local server lifecycle operations only work for server definitions present in `service-definitions/`.

## Relay status

The host app exposes relay status at `/relay/status`.

## Troubleshooting

`/relay/status` shows `configured: false`

- `authority_url` or `access_token` is missing from config

`/relay/status` shows `configured: true` but `connected: false`

- backend is not running on the configured authority URL
- bearer token is invalid or does not verify against backend keys
- desktop host cannot reach the backend over HTTP/WebSocket

`/relay/sessions/me` returns an empty list

- the desktop host never completed `client_hello`
- you are querying the authority with a token for a different user than the desktop host session

the smoke-test script fails with no authority sessions

- the token passed to `smoke-test.ps1` does not belong to the same user represented by the desktop host session
- the desktop host failed before `client_hello` completed

backend starts but local MCP servers do not appear

- confirm JSON files exist under `service-definitions/`
- confirm each definition has a valid `server_id` and `command`
- remember that local MCP servers are advertised as `local-mcp:<server_id>`

persona server mount fails on startup

- confirm the selected persona exists under `servers/`
- confirm any required persona environment variables such as `AGIENCE_API_URI` are present