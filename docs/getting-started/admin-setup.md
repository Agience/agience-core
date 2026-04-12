# Admin Startup Guide (Dev Mode + Seeded Onboarding)

Status: **Reference**
Date: 2026-04-01

Step-by-step guide for an admin doing a **fresh install in dev mode** and curating the **first-run onboarding content** that new users see.

On first login, new users are granted read access to the platform's seed collection (**Agience Inbox Seeds**). It appears in their sidebar and is searchable immediately — no artifact copying. Additional seed collections can be configured via the `SEED_COLLECTION_IDS` environment variable (comma-separated collection keys).

See also:

- [MCP overview](../mcp/overview.md)

---

## 0) Prerequisites

- Docker + Docker Compose
- Python 3.11+ (backend)
- Node.js 18+ (frontend)
- Optional: Google OAuth credentials configured in your `.env` / `.env.local`

For full local setup instructions, see the [Local Development guide](local-development.md).

---

## 1) Start the stack in dev mode (fresh install)

Dev mode means: infrastructure in Docker, backend + frontend running locally.

Fastest path (recommended):

```bash
agience.bat
```

Then open `http://localhost:5173`.

Manual dev path (when you need separate local backend/frontend processes):

1. Start infra containers:

   ```bash
   docker compose up -d graph search
   ```

2. Start backend:

   ```bash
   cd backend
   python main.py
   ```

3. Start frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Expected result:

- Backend starts successfully and, on startup, ensures the seed collection exists (created empty if missing).
- Frontend loads and redirects you to Google auth.

---

## 2) Confirm the seed collection exists

The platform inbox seed collection is created at backend startup (idempotent). You can also force it via CLI:

```bash
cd backend
python manage_seed.py --action seed
```

Expected result:

- **Agience Inbox Seeds** collection exists and is accessible in the sidebar.
- It may be empty on a fresh install (that’s normal).

---

## 3) Create / log in as the admin user (once)

1. Open the app in the browser.
2. Sign in with Google using the admin/dev identity.

Expected result on first login:

- Your account and personal workspace are created automatically.
- A read grant is issued for each configured seed collection — the collection appears in your sidebar immediately.

---

## 3.5) Post-login admin checklist (platform baseline)

After first login, complete this minimal admin checklist:

1. Platform Collection
- Verify the current-instance **Authority** artifact exists and is correct.
- Verify the current-instance **Host** artifact exists and is correct.

2. Seed Collection
- Verify **Agience Inbox Seeds** exists and is intentionally empty on fresh install.
- Grant yourself temporary write access, then curate onboarding artifacts.

3. Settings and keys
- Add provider keys and secrets using the app settings/secrets surfaces.
- Keep sensitive values out of plain environment files where possible.

4. Access model
- Treat this account as the platform admin/operator identity for bootstrap and curation.

---

## 4) Get your `user_id` (required for granting write access)

You need your `user_id` so you can temporarily grant yourself write access to the seed collection.

Option A — decode the JWT (fastest):

1. In browser devtools → Application → Local Storage.
2. Find `access_token`.
3. Decode it (e.g., jwt.io). The `sub` claim is your `user_id`.

Option B - query ArangoDB:

```
FOR p IN people FILTER p.email == 'you@example.com' RETURN p._key
```

---

## 5) Grant yourself write access to “Agience Inbox Seeds”

Run:

```bash
cd backend
python manage_seed.py --action grant-write --user <your-user-id>
```

Expected result:

- Your user can now edit the “Agience Inbox Seeds” collection in the normal UI.
- No backend restart required.

---

## 6) Author the onboarding content as seed artifacts

Open "Agience Inbox Seeds" in the sidebar and add artifacts. Because new users receive a
**read grant** to this collection (not copies), any artifacts you add here become visible
to all users who already have the grant — including anyone who signed up before you
ran `migrate`.

### Recommended seed content

1. **A plain-text "Welcome" or "Getting started" artifact** — introduce the platform.
2. **An Operator artifact with `browse_workspaces`** — easy first tool run (see Step 9).
3. **Optionally, a View artifact pointing at this collection** — helps users understand
   they're looking at a shared platform collection, not personal content.

### What users see

- "Agience Inbox Seeds" appears in the sidebar under **Collections** for every new user.
- Artifacts inside it are immediately searchable.
- Users only have read access — they cannot edit or delete these artifacts.

### Notes

- To register an external MCP server for a workspace, create an artifact with content type
  `application/vnd.agience.mcp-server+json`. The artifact's `context.transport` field defines
  how to connect (HTTP `well_known` URL or `stdio` command). See [MCP Overview](../mcp/overview.md) for the full transport schema.
- Artifacts in the seed collection are **live** — edits you make are visible to all users
  immediately (unlike copies, which would be frozen at the time of first login).

---

## 7) (Optional) Revoke your write access when done

```bash
cd backend
python manage_seed.py --action revoke --user <your-user-id>
```

Expected result:

- Your account returns to read-only access for the seed collection.

---

## 8) Test the experience as a brand new user

1. Log out.
2. Log in with a brand new Google identity.

Expected result:

- The new user sees "Agience Inbox Seeds" in their sidebar under **Collections**.
- Artifacts in the seed collection are searchable immediately.
- The new user has read-only access (cannot edit seed artifacts).

---

## 9) Run a very simple tool via an Operator (current UI)

This verifies "tools exist" and "operators can run a tool" end-to-end.

### Why this works

The Operator runner's generic tool path currently calls an MCP tool with only:

```json
{ "workspace_id": "<current-workspace-id>" }
```

So pick a tool that accepts `workspace_id`.

### Steps

1. In the user's Inbox workspace, create an artifact of type **Operator** (content type: `application/vnd.agience.transform+json`).
2. Open the Operator artifact (it renders the palette/operator runner UI).
3. Open the **Tools** panel.
4. Select the MCP tool `browse_workspaces`.
5. Click **Run**.

Expected result:

- The operator produces a "Palette output" artifact showing the tool ran.
- The output context contains the tool result payload.

If you do not select a tool, the runner defaults to `extract_information`, which requires at least one selected source artifact.

---

## 10) Troubleshooting checklist

- **Seed collection not visible to new user**: ensure the backend started without errors and the collection exists (`python manage_seed.py --action seed`). The grant is issued automatically on first login.
- **Can’t edit seed collection**: confirm you ran `grant-write` with the correct `user_id`.
- **Operator tool fails**: ensure you selected `browse_workspaces` (accepts `workspace_id`). Many tools will fail if you pass unexpected args.
- **Seed changes not visible to existing users**: run `python manage_seed.py --action migrate`.
