# CI/CD Pipeline & Host Deployment

Status: **Reference**
Date: 2026-04-01

---

## Overview

Agience uses a build-once, deploy-anywhere model. `agience-core` is the application source of truth. CI validates branch changes, branch publishes produce integration and release-line images, and stable Git tags publish the official release images.

Host repos such as `agience-host-my` remain deployment-only. They pull already-built Docker Hub images and should pin explicit tags in `.env`.

```
agience-core (GitHub)
    │
    ├── push to main         ──▶ CI ──▶ publish canary images
    ├── push to release/X.Y  ──▶ CI ──▶ publish release-line images
    └── push tag vX.Y.Z      ──▶ publish stable images
                                                 │
                                     ┌───────────┼───────────┐
                                     ▼           ▼           ▼
                              agience-host-my   brand hosts   test hosts
                              pinned tags       pinned tags   pinned tags
```

---

## Container registries

Images publish to Docker Hub and GitHub Container Registry (GHCR).

Current repositories:

| Docker Hub Repository | Image |
|---|---|
| `${REGISTRY}/agience-backend` | FastAPI backend |
| `${REGISTRY}/agience-frontend` | React frontend |
| `${REGISTRY}/agience-servers` | Unified server host |
| `${REGISTRY}/agience-stream` | Astra stream ingest |

GHCR mirrors the same images under:

- `ghcr.io/<owner>/agience-backend`
- `ghcr.io/<owner>/agience-frontend`
- `ghcr.io/<owner>/agience-servers`
- `ghcr.io/<owner>/agience-stream`

Required GitHub Actions secrets:

| Secret | Purpose |
|---|---|
| `DOCKERHUB_NAMESPACE` | Docker Hub namespace (user or org that owns image repos) |
| `DOCKERHUB_TOKEN` | Docker Hub access token |

The current workflow publishes into the namespace defined by `DOCKERHUB_NAMESPACE`.

---

## Branch & release model

The branch model is:

- `feature/**` and `dev/**`: active development
- `main`: integration branch
- `release/X.Y`: stabilization branch for release line `X.Y`
- `hotfix/**`: targeted fixes that merge back into the release line and then into `main`

Publishing behavior:

- `main` publishes canary images automatically after CI passes
- `release/X.Y` publishes release-line images automatically after CI passes
- stable Git tags `vX.Y.Z` publish the official release images
- prerelease Git tags are not used

After shipping a release, merge the release branch back into `main`.

### Freeze flow (recommended)

When you want a release freeze:

1. Cut `release/X.Y` from `main`.
2. Keep accepting feature PRs to `main` for the next version.
3. During freeze, target only release fixes at `release/X.Y`.
4. Tag stable `vX.Y.Z` from `release/X.Y` (not from `main`).
5. Merge `release/X.Y` back into `main` after the release to prevent drift.

---

## Version source of truth

`build_info.json` is the human-visible product version.

Rules:

- Do not change it for every branch build
- Change it when the intended shipped product version changes
- Stable Git tags must match it exactly

Example:

- `build_info.json = 1.1.0` requires stable Git tag `v1.1.0`

If the stable tag and `build_info.json` do not match, stable publishing fails.

---

## Image tagging strategy

| Image tag | Source | Meaning |
|---|---|---|
| `canary` | push to `main` | latest integration build |
| `main-<sha>` | push to `main` | pinned integration build |
| `X.Y-rc` | push to `release/X.Y` | latest build on release line `X.Y` |
| `X.Y-<sha>` | push to `release/X.Y` | pinned build on release line `X.Y` |
| `latest` | Git tag `vX.Y.Z` | current stable production release |
| `X.Y` | Git tag `vX.Y.Z` | current stable release for line `X.Y` |
| `X.Y.Z` | Git tag `vX.Y.Z` | pinned stable release |

Rules:

- `latest` is reserved for stable releases only
- `main` never publishes `latest`
- `release/X.Y` never publishes `latest`
- production hosts should pin explicit image tags in `.env`

---

## Workflow behavior

Workflow files:

- `agience-core/.github/workflows/ci.yml`
- `agience-core/.github/workflows/build-and-push.yml`

### CI workflow

`ci.yml` runs on:

- push to `main`
- push to `dev/**`
- push to `feature/**`
- push to `release/**`
- push to `hotfix/**`
- pull requests targeting `main`, `dev/**`, and `release/**`

It runs backend, frontend, and docs validation only when the relevant areas changed.

When the event is a push to `main` or `release/**`, and publish-relevant files changed, CI calls the reusable publish workflow after validation passes.

### Publish workflow

`build-and-push.yml` has two entry points:

- reusable invocation from CI for `main` and `release/**` branch publishing
- direct trigger on pushed stable tags matching `v*`

The workflow:

- checks out the exact commit being published
- reads `build_info.json`
- validates stable tags against `build_info.json`
- rejects prerelease Git tags
- logs in to Docker Hub
- builds and pushes backend, frontend, servers, and stream images

The frontend image remains environment-agnostic. Host repos provide runtime environment values such as backend URI, title, and branding.

### Stable release helper

Use the helper only for stable releases:

```bash
python .scripts/create_release_tag.py
python .scripts/create_release_tag.py --create
git push origin vX.Y.Z
```

The helper reads `build_info.json`, refuses prerelease versions, previews the matching stable tag, and can create the local annotated tag for you.

---

## Host repo pattern

Each host repo is deployment config only. It contains a compose file, edge proxy config, and environment values. It does not build application images.
    docker-compose.yml      # pulls images, no build: directives
    Caddyfile               # reverse proxy config for this domain
    .env.example            # documents all required env vars
    README.md               # deployment instructions for this host
    .gitignore              # ignores .env (secrets never committed)
```

A concrete starter lives in the [`agience-home`](https://github.com/agience/agience-home) repo.

The `.env` file on the server (never committed) sets explicit image tags:

```env
REGISTRY=agience
BACKEND_IMAGE=${REGISTRY}/agience-backend:1.2.3
FRONTEND_IMAGE=${REGISTRY}/agience-frontend:1.2.3
SERVERS_IMAGE=${REGISTRY}/agience-servers:1.2.3
STREAM_IMAGE=${REGISTRY}/agience-stream:1.2.3
DOMAIN=app.example.com
API_DOMAIN=api.example.com
VITE_BACKEND_URI=https://api.example.com
VITE_CLIENT_ID=
# ... all other required vars
```

Deploying a new release is:

```bash
docker compose pull
docker compose up -d
```

That is all the host needs.

---

## Host roster

| Host repo | Operator | Instance purpose | Release tracking |
|---|---|---|---|
| `agience-home` | Agience | Example self-host starter | pinned tag |
| `agience-host-app` | Agience | SaaS main app authority instance | pinned tag |
| `agience-host-astra` | Agience | (reserved — future Astra-specific host) | TBD |
| `agience-host-verso` | Agience | (reserved — future Verso-specific host) | TBD |
| `ikailo-host-aria` | Ikailo | Pinned release testing + Aria server sidecar | pinned tag |
| `foresight-host-sage` | Foresight | White-labeled research agent product | pinned tag |
| `questify-host-nexus` | Questify | DevOps subscription product (spawns instances) | pinned tag |

### Hosts with server sidecars

Some host repos add one or more MCP servers as additional services alongside the core stack. The server images are pulled directly from the server repos' own CI once those pipelines exist.

Example — `ikailo-host-aria` adds the Aria server:

```yaml
services:
  # ... core agience-core services (backend, frontend, etc.) ...

  aria:
    image: ${ARIA_IMAGE}
    container_name: aria
    restart: unless-stopped
    env_file: .env
    environment:
      - AGIENCE_API_URI=http://backend:8081
      - PLATFORM_INTERNAL_SECRET=${PLATFORM_INTERNAL_SECRET}
      - SRS_HTTP_API=http://stream:1985
    depends_on:
      backend:
        condition: service_healthy
```

---

## Pinned deployment flow

1. Developer prepares a release branch and sets `build_info.json` to a release or prerelease version.
2. Developer creates and pushes the matching stable Git tag `v1.2.3`.
3. CI validates the tag/version match and pushes the images to Docker Hub.
4. On the host, operators set explicit image tags in `.env`.
5. Deploy or update the host:
   ```bash
   docker compose pull
   docker compose up -d
   ```
6. Production hosts stay on pinned tags until operators deliberately update them.

---

## Server image publishing

Each `agience-server-*` repo will have its own GitHub Actions workflow mirroring the pattern above, publishing to:

```
{DOCKERHUB_NAMESPACE}/agience-server-aria:latest
{DOCKERHUB_NAMESPACE}/agience-server-aria:1.2.3
{DOCKERHUB_NAMESPACE}/agience-server-sage:latest
# etc.
```
