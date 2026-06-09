# Run, Release & Deploy

Status: **Reference**
Date: 2026-06-07

The operator runbook for three things:

1. **Run locally** — `agience.bat`
2. **Cut releases** — version, tag, build images
3. **Deploy hosted sites** — my.agience.ai and other tenants

Agience uses a **build-once, deploy-anywhere** model. `agience-core` is the
application source of truth: it builds the images. Hosted sites are
deployment-only repos that pull already-built images and run `docker compose`.

```
agience-core (private)
    ├── push to main         ──▶ CI ──▶ :edge images
    ├── push to release/X.Y  ──▶ CI ──▶ :stable-rc + :X.Y-rc-<sha7> images
    └── tag vX.Y.Z           ──▶ CI ──▶ :stable :X.Y :X.Y.Z images  (Docker Hub + GHCR)
                                                  │
                                  ┌───────────────┼───────────────┐
                                  ▼               ▼               ▼
                            agience-prod-infra  agience-host-my   foresight tenant
                            (shared Caddy)      (my.agience.ai)   (foresightreports…)
```

---

## 1. Run locally — `agience.bat`

From the repo root (`.\agience.bat <mode> [options]`):

| Command | What it does |
|---|---|
| `.\agience.bat dev -f` | **Daily driver.** Infra + origin + chorus in Docker; **mantle + facet run locally** (your code, live-reload). |
| `.\agience.bat dev -f --reset` | Same, but factory-resets `.data` first → setup wizard → seeds + post-setup reindex. |
| `.\agience.bat full` | Everything in Docker (uses locally-built images). |
| `.\agience.bat full -b` | Full, **rebuild** images first (picks up code changes). |
| `.\agience.bat test` | Precheck: mantle + facet lint & tests (`.scripts/precheck.ps1`). |
| `.\agience.bat down` | Stop all containers. |

Backend `http://localhost:8081`, frontend `http://localhost:5173`. First `dev`
run creates `src/mantle/.venv` and installs deps; `-i` forces a dependency
refresh, `--clean-deps` rebuilds the venv + `node_modules` from scratch.

`--reset` wipes the database, object store, and RSA keys, then drops you into
the first-run setup wizard. See [Local Development](../getting-started/local-development.md)
and [Admin Setup](../getting-started/admin-setup.md).

---

## 2. Container registries & image tags

Each stable release publishes **7 images** to **Docker Hub** (`${REGISTRY}/…`,
default namespace `agience`) and mirrors them to **GHCR**
(`ghcr.io/<owner>/…`). Embeddings is **not** in the suite — it's an external
service (see caveats):

| Image | Service |
|---|---|
| `agience-origin` | FastAPI identity service (OIDC, grants, passkeys) |
| `agience-mantle` | FastAPI artifact kernel + encrypted MANTLE/SSE search |
| `agience-chorus` | FastMCP unified persona host + universal MCP gateway |
| `agience-facet` | React SPA (environment-agnostic; host supplies runtime env) |
| `agience-stream` | Astra stream ingest (SRS RTMP) |
| `agience-init` | One-shot init container (key + password generation) |
| `agience-home` | Caddy + cert-bootstrap image for the self-host starter |

Required GitHub Actions secrets: `DOCKERHUB_NAMESPACE`, `DOCKERHUB_TOKEN`
(GHCR uses `GITHUB_TOKEN`).

**Tag matrix:**

| Tag | Source | Meaning |
|---|---|---|
| `:edge` , `:edge-<sha7>` | push to `main` | latest integration build (rolling + per-commit pin) |
| `:stable-rc` | push to `release/X.Y` | latest release-candidate across release lines |
| `:X.Y-rc-<sha7>` | push to `release/X.Y` | pinned RC on line `X.Y` |
| `:stable` | tag `vX.Y.Z` | current stable production release (moving pointer) |
| `:X.Y` | tag `vX.Y.Z` | latest stable on line `X.Y` |
| `:X.Y.Z` | tag `vX.Y.Z` | pinned stable release |

`:stable` is reserved for stable releases — `main` and `release/*` never publish
it. Production hosts that want determinism pin `:X.Y.Z` (see §5).

---

## 3. Branch & version model

```
feature/** , dev/**   active development
        │
        ▼
      main              integration; publishes :canary
        │
        ▼
   release/X.Y          stabilization for line X.Y; publishes :*-rc
        │
        ▼
   tag vX.Y.Z           official release; publishes :stable :X.Y :X.Y.Z
```

**`build_info.json` is the version source of truth** (the human-visible product
version). Change it only when the shipped version changes; a stable tag `vX.Y.Z`
**must** equal `build_info.json` exactly or stable publishing fails. Prerelease
Git tags are not used — RCs come from `release/*` branches, not tags.

> Releases are cut from `main`. If you've been working on `dev/<you>`, merge it
> into `main` first.

---

## 4. Cut a release

The release scripts live in `.scripts/` and are exposed as **VS Code tasks**
(Ctrl+Shift+P → *Run Task*). Run from the repo root.

| Step | VS Code task | Script |
|---|---|---|
| Cut a release line | **Agience: RC — Cut Branch** | `cut-release.ps1 -Version X.Y` |
| Tag a stable release | **Agience: Stable — Tag Release** | `tag-stable.ps1 -Version X.Y.Z` |
| Create / finish a hotfix | **Agience: Hotfix — Create / Finish** | `hotfix.ps1 -Version X.Y.Z [-Finish -ForwardPort]` |
| Pull `main` into a release line | **Agience: Release — Pull Main In** | `promote_main.ps1 -Base release/X.Y -Head main` |
| Publish source to the public mirror | **Agience: Edge — Publish** | `publish_public.ps1` |

**a) Cut a release line** — `cut-release.ps1 -Version 0.3`
Must be on `main`. Creates `release/0.3`, stamps `build_info.json` = `0.3.0`,
commits, pushes. CI then builds `:stable-rc` + `:0.3-rc-<sha7>`. Stabilize on
this branch (hotfixes / cherry-picks); keep merging features to `main` for the
next line.

**b) Tag stable** — `tag-stable.ps1 -Version 0.3.0`
Bumps `build_info.json` to match if needed, tags `v0.3.0`, pushes `release/0.3`,
**forward-ports `release/0.3` → `main`**, then runs `publish_public.ps1` to push
the tag to the public mirror. The tag triggers:

- `build-and-push-ghcr.yml` → all 8 images at `:stable :0.3 :0.3.0` (Docker Hub + GHCR)
- `release.yml` → GitHub Release with notes

**c) Hotfix** — `hotfix.ps1 -Version 0.2.1` then `… -Finish -ForwardPort`.
Patch an existing `release/X.Y` without routing through `main`; `-Finish`
forward-ports the fix back into `main`.

### Workflow reference

| Workflow | Trigger | Effect |
|---|---|---|
| `ci.yml` | push to `main`/`dev/**`/`feature/**`/`release/**`/`hotfix/**`, PRs | lint + tests; on `main`/`release/**` calls the publish workflow |
| `build-and-push.yml` | reusable (from CI) | builds `:canary` / `:*-rc` branch images |
| `build-and-push-ghcr.yml` | push tag `v*` | builds `:stable :X.Y :X.Y.Z` to Docker Hub + GHCR |
| `release.yml` | push tag `v*` | GitHub Release notes |
| `cut-release.yml` / `tag-stable.yml` / `hotfix-merge.yml` | — | CI-side counterparts of the local scripts |

---

## 5. Deploy hosted sites

**Topology.** One production box runs a **shared Caddy** (`agience-prod-infra`)
on an external Docker network named `agience`. Each tenant is its **own compose
stack** that joins that network; Caddy routes by hostname to the tenant's
containers. Tenants are isolated by compose project, container-name prefix, and
data path — but share the box, the network, and the `agience/*` images.

| Repo (local working dir) | Serves | Project / data |
|---|---|---|
| `agience-prod-infra` | shared Caddy + `agience` network | — |
| `agience-host-my` (`my-agience-ai`) | my.agience.ai | `agience-*`, `/var/lib/my-agience` |
| Foresight tenant (`foresight-my-agience-ai`) | foresightreports.my.agience.ai | `foresight-*`, `/var/lib/foresight` |

Each host repo has a `release.yml` that SSHes to the box and runs
`docker compose pull && docker compose up -d`, resolving image versions from its
**`manifest.yml`** (`registry:` + `version:`, default `version: stable`). The
exact domain, image pins, and secrets live in each host repo's `manifest.yml`,
`<domain>.caddy`, and server-side `.env` (never committed).

**First-time order:** deploy `agience-prod-infra` (creates the network + Caddy)
→ `agience-host-my` → the Foresight tenant.

**Routine deploy** (after a stable tag — `:stable` now points at the new build):

- **my.agience.ai** — VS Code task **Agience: My — Deploy**
  (`gh workflow run deploy-suite.yml --repo Agience/agience-core-private`).
  `deploy-suite.yml` dispatches `agience-host-my`'s `release.yml` on its
  `release` ref.
- **Foresight / any other tenant** — there is no core shortcut: trigger that
  tenant repo's own `release.yml` (GitHub → Actions → *Run workflow*, or push
  its `release` branch).

**Pin / roll back.** Edit `manifest.yml` in the tenant repo (set `version:` to
`0.3.0` instead of `stable`), commit to `release`, redeploy. Revert the commit
to roll back.

**Add a tenant.** Clone a host repo; set its `<domain>.caddy`, `manifest.yml`,
data path, and server `.env` (DOMAIN, OAuth, secrets); add a DNS A record to the
box; deploy. The shared Caddy picks up the new `conf.d/<domain>.caddy` snippet on
reload.

### Self-host flavors (single box)

For a single box (not the managed multi-tenant setup), the installer
(`package/install/install.ps1` / `install.sh`) offers two compose flavors that
pull the published `:stable` images:

- **Home** (`package/install/home/`) — Caddy with **automatic TLS** on your own
  domain (the `agience-home` image fetches the cert at startup). For a public
  install with a domain.
- **Plain** (`package/install/plain/`) — bare Caddy, **HTTP only, no domain**
  (`http://localhost:8080`). For local / LAN / behind-your-own-proxy.

See [Deploy to EC2](../getting-started/deploy-ec2.md) and
[Self-Hosting](../getting-started/self-hosting.md). The release notes label the
run targets **Local / Home / Dev / My / Hosted**.

---

## 6. Operator caveats

- **Releases come from `main`** — merge your `dev/*` branch in before cutting.
- **Embeddings is external.** No stack bundles an embeddings container — set
  `EMBEDDINGS_URI` (server `.env` / tenant `manifest`) to a reachable `/embed`
  endpoint, e.g. a managed GPU host running `src/embeddings/`
  (`package/docker/embeddings.gpu.Dockerfile` builds the CUDA image). Unset →
  search degrades to lexical-only. See [Search](../features/search.md).
- **Back up `/var/lib/<tenant>/.data/keys`** on the box — JWT + encryption keys
  live there; losing them orphans every encrypted MANTLE cell.
- **Self-host hosts pin explicit tags** (`:X.Y.Z`); the managed tenants track
  `:stable` via `manifest.yml`.
