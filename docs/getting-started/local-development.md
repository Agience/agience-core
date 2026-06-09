# Local Development Setup

Status: **Reference**
Date: 2026-04-10

This guide walks a developer through running Agience locally from source: infrastructure containers, backend, frontend, and (optionally) the desktop relay host. It is not a production or self-hosting guide — see `docs/getting-started/self-hosting.md` for that.

> **Just want to run Agience?** Use the [home install](https://github.com/Agience/agience-home) — one command, pre-built images, no build tools needed.

---

## Quick Start

The fastest path for developers:

```bash
git clone https://github.com/Agience/agience-core.git
cd agience-core
```

**Windows:**
```
agience dev -f --build
```

**Linux / macOS:**
```bash
./agience dev -f --build
```

This will:
1. Check that Docker, Python, and Node.js are installed
2. Start support containers (ArangoDB, Postgres, MinIO, init) in Docker
3. Create Python virtual environments under `src/origin/.venv` and `src/mantle/.venv` and install dependencies
4. Install Facet npm dependencies
5. Launch Origin, Mantle, Chorus, and Facet in a new terminal window

On **first boot**, the init container generates all credentials (encryption keys, database passwords, service identity keypairs, setup token). Open `http://localhost:5173` — the setup wizard walks you through OAuth login and LLM provider configuration. No `.env` file is required.

---

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Git** | any recent | version control |
| **Docker Desktop** | latest stable | includes Docker Compose v2 |
| **Python** | 3.11+ | backend runtime |
| **Node.js** | 20+ | frontend build/dev server |
| **npm** | bundled with Node | frontend package management |

**Windows note**: Docker Desktop for Windows requires either WSL 2 or Hyper-V. WSL 2 is recommended. Verify Docker is running before proceeding:

```powershell
docker info
```

**Python note**: The `agience` launcher creates separate venvs under `src/origin/.venv` and `src/mantle/.venv` (one per service tree). If you run a service manually, activate the venv for that tree first:

```powershell
src\mantle\.venv\Scripts\Activate.ps1    # Windows PowerShell
# sourcemantle/ mantle/.venv/bin/activate    # bash / Git Bash
```

---

## 2. Clone and Configure

### Clone the repository

```bash
git clone https://github.com/Agience/agience-core.git
cd agience-core
```

### Configuration

**Zero-config (recommended):** The init container generates all credentials on first boot. The setup wizard (browser) configures OAuth login, LLM provider, and access control. No `.env` file needed.

**Manual override (optional):** If you prefer to set environment variables directly, copy the template and edit:

```powershell
Copy-Item .env.example .env.local
```

Each service reads `.env.local` first (local/test), then `.env` (Docker defaults), then falls back to database settings from the setup wizard. For most developers, the setup wizard is sufficient.

---

## 3. Start Infrastructure (Dev Mode)

The `agience dev` command handles everything. For manual control:

Dev mode starts the support services (databases + object store + init) in Docker, leaving Origin, Mantle, Chorus, and Facet running as local processes for faster iteration.

```bash
docker compose --project-directory . \
  -f package/docker/docker-compose.yml \
  -f package/docker/docker-compose.override.yml \
  up -d content graph
```

On Windows PowerShell (no line continuation needed, or use backtick):

```powershell
docker compose --project-directory . `
  -f package/docker/docker-compose.yml `
  -f package/docker/docker-compose.override.yml `
  up -d content graph
```

Wait for both containers to reach a healthy state:

```bash
docker ps
```

Expected output (abbreviated):

```
CONTAINER ID   IMAGE                    STATUS
...            arangodb:3.11            Up ... (healthy)
...            minio/minio:RELEASE...   Up ... (healthy)
```

**What each support service is:**

| Service name | Technology | Purpose | Local port |
|---|---|---|---|
| `graph` | ArangoDB | Unified artifact storage (workspaces + collections) | 8529 |
| `sql` | Postgres | Origin identity DB (Person / APIKey / Grant / ...) | 5432 |
| `content` | MinIO | S3-compatible object store (artifact content + MANTLE+SSE encrypted blobs) | 9000 |

These ports are intentionally non-standard to avoid collisions with other local services. Search runs in-process inside Mantle on encrypted MANTLE+SSE blobs in MinIO — there is no separate search container after Step 2.6.9.

**Stopping the infrastructure:**

```bash
docker compose --project-directory . \
  -f package/docker/docker-compose.yml \
  -f package/docker/docker-compose.override.yml \
  down
```

---

## 4. Run the Services

In separate terminals, with the appropriate venv active:

```bash
# Origin (identity, port 8080)
cdmantle/ origin
.venv/Scripts/activate        # Windows — or: source .venv/bin/activate (bash)
pip install -r requirements.txt
python main.py

# Mantle (artifact kernel, port 8081)
cdmantle/ mantle
.venv/Scripts/activate
pip install -r requirements.txt
python main.py

# Chorus (MCP gateway + persona host, port 8082)
cdmantle/ chorus
python server.py
```

> **Tip**: If you used `agience dev`, the venvs are already created and dependencies are installed. Just activate them.

**First-run behavior**: On the first startup:

1. Origin creates Postgres tables via Alembic, seeds the bootstrap operator
2. Mantle creates ArangoDB collections + indexes; the encrypted MANTLE+SSE indexes auto-bootstrap on first commit
3. Each service signs platform-default artifacts (LLM connections, authority, host, etc.) on first launch

You will see log output for each step. If a support container isn't yet healthy, the services retry automatically for a short window. If startup fails, check `docker ps` to confirm graph + sql + content are running and healthy.

**Log level**: Set `BACKEND_LOG_LEVEL=DEBUG` in `.env.local` for verbose output during development.

**Interactive API docs**:

```
http://localhost:8080/docs   # Origin
http://localhost:8081/docs   # Mantle
```

---

## 5. Run Facet

In one more terminal:

```bash
cdmantle/ facet
npm install
npm run dev
```

The dev server starts at `http://localhost:5173` and proxies API calls to Origin (`:8080`) and Mantle (`:8081`).

**What `npm run dev` does:**

- Vite reads `build_info.json` and injects `__APP_VERSION__` as a compile-time define
- Starts the Vite HMR (Hot Module Replacement) dev server
- Opens `http://localhost:5173` — navigate there in your browser

**First login**: Click "Sign in with Google", authenticate, and you will be redirected back to the app. If you see "Access denied", your email or domain is not in the access control settings (configured via the setup wizard, or `ALLOWED_EMAILS` / `ALLOWED_DOMAINS` in `.env.local`).

After first login, the backend provisions your user's inbox, workspace, and seed collections automatically.

---

## 6. Desktop Relay Host (Optional)

The desktop relay host is an optional local companion runtime that:

- Exposes the first-party MCP persona servers locally (Aria, Sage, Mantle, etc.)
- Provides safe read-only filesystem tools via MCP
- Can maintain a relay connection to a running backend authority

This is only needed if you are working on the desktop host itself, testing local MCP persona servers, or developing features that use the relay protocol.

### Install

From the repo root:

```powershell
Set-Location hosts\desktop
python -m pip install -e .
```

### Configure

Copy `hosts/desktop/config.example.json` to a local config file and edit:

```json
{
  "mode": "host",
  "authority_url": "http://localhost:8081",
  "access_token": "<agience access token from local sign-in>",
  "bind_host": "127.0.0.1",
  "bind_port": 8082,
  "allowed_roots": [
    "C:/Users/yourname/Documents"
  ],
  "enabled_personas": ["aria", "sage", "iris", "astra", "verso", "seraph", "ophan"],
  "log_level": "INFO"
}
```

### Start

```powershell
python -m agience_relay_host.main --config .\config.example.json
```

For full setup instructions, token generation steps, and troubleshooting, see `hosts/desktop/README.md`.

---

## 7. Verify

Work through this checklist after starting the full stack.

**Backend health**

```bash
curl http://localhost:8081/version
```

Expected: a JSON object with `version` and build metadata.

```bash
curl http://localhost:8081/.well-known/mcp.json
```

Expected:
```json
{"endpoints": {"streamable_http": "/mcp"}}
```

**FastAPI docs**

Open `http://localhost:8081/docs` in your browser. You should see the Swagger UI with all routers listed.

**Frontend**

Open `http://localhost:5173`. The Agience UI should load. If it shows a blank page, check the browser console for errors (usually a missing backend URL or CORS issue).

**Login flow**

1. Click Sign In
2. Complete Google OAuth
3. You should land in the Agience workspace with your inbox seeded

**MCP endpoint**

```bash
curl -H "Authorization: Bearer <your-token>" \
     http://localhost:8081/mcp
```

Expected: an HTTP 200 or SSE response (not a 401 or 404).

**Database containers**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

All containers (`graph`, `search`) should show `(healthy)`.

---

## 8. Run Tests

### Mantle / Origin (Python)

From `src/mantle/` (or `src/origin/`):

```bash
# Lint
pip install ruff
ruff check .

# Tests
pytest tests/
```

Run a specific suite:

```bash
pytest tests/test_router_artifacts.py
pytest tests/test_service_workspace.py
```

Run with verbose output:

```bash
pytest tests/ -v
```

**Note**: Tests use mocked databases and never connect to live ArangoDB, Postgres, or S3. No running containers are required for the test suite.

### Facet

From `src/facet/`:

```bash
# Lint
npm run lint

# Tests (Vitest + React Testing Library)
npm run test

# Tests in watch mode
npm run test -- --watch
```

### Full pre-push gate

Run both suites before pushing a branch. CI enforces the same commands on `main`.

```bash
# Backend
cd backend && ruff check . && pytest tests/

# Frontend
cd frontend && npm run lint && npm run test
```

On Windows PowerShell in two separate steps:

```powershell
Set-Location backend; ruff check .; pytest tests/
Set-Location ..\frontend; npm run lint; npm run test
```

---

## 9. Troubleshooting

### Backend won't start — "database connection refused"

The database containers are not yet healthy. Check:

```bash
docker ps
```

If containers are missing, start them again (section 3). If they are present but not healthy, check their logs:

```bash
docker logs agience-core-graph-1
docker logs agience-core-content-1
docker logs agience-core-sql-1
```

Common cause: ArangoDB or Postgres takes 30–60 seconds to initialize on first boot. Origin / Mantle retry, but if they time out, restart the affected service after the support container becomes healthy.

### "Access denied" after Google login

Your email is not in the allowlist. Either re-run the setup wizard and add your email, or add it to `.env.local`:

```dotenv
ALLOWED_EMAILS=your-actual-email@gmail.com
```

Restart the backend after editing `.env.local`.

### Frontend shows blank page or API 401 errors

Check that the backend is running at `http://localhost:8081`. If you used `.env.local`, verify `VITE_BACKEND_URI` is set to `http://localhost:8081`. Also verify the JWT in `localStorage` is not expired (12-hour lifetime); log out and back in to refresh it.

### `npm run dev` fails — "Cannot find module"

Node modules are missing or stale:

```bash
cd frontend
rm -rf node_modules package-lock.json   # bash / Git Bash
npm install
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
```

### `ruff check` reports errors

Fix lint errors before running tests:

```bash
cd backend
ruff check . --fix      # auto-fix safe issues
ruff check .            # verify remaining issues
```

### `pytest` fails with import errors

Your Python path may be off. Run pytest from inside the service tree (`src/mantle/` or `src/origin/`):

```bash
cdmantle/ mantle
pytest tests/
```

If that still fails, confirm your venv is active (`which python` on bash, `Get-Command python` on PowerShell) and that `pip install -r requirements.txt` completed without errors.

---

## Related Docs

- [Self-hosting](self-hosting.md) — production/VPS deployment
- [Admin setup](admin-setup.md) — first-admin provisioning
- [Best practices](../guides/best-practices.md) — code style and architecture patterns
