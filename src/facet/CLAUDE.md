# Facet — Claude Code Instructions

Status: **Reference**
Date: 2026-05-07

See root `CLAUDE.md` for vocabulary, architecture overview, and global rules.

This directory was renamed `frontend/` → `src/facet/` in Step 1.5 of
the four-container migration (2026-05-07; finalized under the `src/`
umbrella in Step G.3). Component paths inside still say
"frontend/src/..." in some file-header comments — those are doc strings
left from the rename, not module paths. Imports are unaffected.

The `api/` modules call three backends:
- `mantle/` (artifacts, search, events) — `VITE_MANTLE_URI`
- `origin/` (auth, identity, grants, OTP, passkey) — `VITE_ORIGIN_URI`
- Chorus tools are reached **through** Mantle's `/mcp` gateway, never directly

---

## Stack

- **React 19** + **TypeScript 5.7**
- **Vite** — build tool, dev server (localhost:5173)
- **Vitest** + React Testing Library — unit/component tests
- **Tailwind CSS** + **shadcn/ui** (Radix UI primitives)
- **React Router** — client-side routing
- **Axios** — HTTP client with auth interceptors

---

## Directory Structure

```
src/facet/src/
├── api/             # Typed API client modules (always use these — never direct fetch())
│   ├── api.ts       # Axios instance with auth interceptors + 401 handling
│   ├── workspaces.ts, collections.ts, agent.ts, mcp.ts, search.ts, ...
│   └── types/       # API type definitions (artifact.ts, workspace.ts, collection.ts, ...)
├── auth/            # Auth context, hooks, OAuth flow
├── components/      # Shared/reusable React components
│   └── ui/          # shadcn/ui component wrappers
├── config/          # Feature flags, app configuration
├── constants/       # Application-wide constants
├── content-types/   # Legacy compiled handlers being retired; do not add new entries
├── context/         # React Context providers
│   ├── workspace/   # WorkspaceProvider — single source of truth for artifact state
│   ├── auth/        # AuthProvider — JWT, login state
│   └── palette/     # PaletteProvider — command palette
├── dnd/             # Drag-and-drop utilities
├── hooks/           # Custom React hooks
├── isolation/       # Sandbox host for server-owned ui:// viewers
├── lib/             # Utility libraries
├── pages/           # Top-level page components
├── product/         # Product-specific features
├── registry/        # Type registry and viewer dispatch
├── routes/          # Route definitions
├── types/           # Global TypeScript type definitions
└── utils/           # Utility functions
```

---

## State Management

### WorkspaceContext is the Single Source of Truth

```typescript
// Always read from context
const { selectedCardIds, cards, updateCard } = useWorkspace();

// NEVER duplicate workspace state in local component state
// ❌ const [selectedCardIds, setSelectedCardIds] = useState<string[]>([]);
```

Relevant providers:
- `WorkspaceProvider` — artifact state, card selection, CRUD
- `AuthProvider` — JWT token, user identity
- `PaletteProvider` — command palette open/close state

### API Calls

**Always use typed API functions from `src/facet/src/api/`. Never call `fetch()` directly.**

```typescript
// ✅ GOOD — auth interceptors, error handling, typing included
import { initiateUpload } from '../api/workspaces';
const result = await initiateUpload(workspaceId, { filename, mime, size });

// ❌ BAD — bypasses auth and error handling
const result = await fetch('/api/workspaces/...');
```

JWT is stored in `localStorage` as `access_token`. The Axios instance in `api/api.ts` injects it automatically.

---

## Content Type System

Agience is moving to server-owned handlers and viewers.

Current structure:
1. Builtin type skeletons live under `package/types/<top-level>/<subtype>/type.json`
2. Server-owned type definitions and viewers live under `src/chorus/<persona>/ui/...`
3. Facet resolves viewers through `src/facet/src/registry/` and hosts them through `src/facet/src/isolation/`

Important boundary:
- `src/facet/src/content-types/` is a legacy area kept for existing compiled handlers during the transition
- Do not add new viewer packages there
- New vendor or Agience-specific viewers should be served by the owning MCP server as `ui://` resources

Frontend code should stay type-oblivious outside the registry and isolation layers.

---

## Component Patterns

### Composition Over Props Drilling

```typescript
// ✅ GOOD
<ThreeColumnLayout
  leftPanel={<Sidebar />}
  centerPanel={<Browser />}
  rightPanel={<PreviewPane />}
/>

// ❌ BAD — prop drilling through 3+ layers
<Layout sidebarItems={items} onSidebarClick={fn} browserCards={cards} ... />
```

### Single Responsibility

- If a component is >300 lines, consider splitting
- Each component should do one thing
- Use context + composition; avoid god components

### Consistent Interfaces

Grid and List views should accept the same props so they're swappable:
```typescript
interface CardItemProps {
  card: Card;
  isSelected: boolean;
  onSelect: (id: string) => void;
}
```

---

## React Pitfalls (from Production)

### Arrays/Objects in useEffect Dependencies → Infinite Loops

```typescript
// ❌ BAD — array reference changes every render → infinite loop
useEffect(() => { ... }, [open, selectedCollectionIds]);

// ✅ GOOD — primitive only
useEffect(() => { ... }, [open]);
```

### Hooks Before Early Returns

```typescript
// ❌ BAD — hook after early return
function Component({ card }) {
  if (!card) return null;
  const ctx = useMemo(() => parse(card), [card]); // never reached
}

// ✅ GOOD
function Component({ card }) {
  const ctx = useMemo(() => { if (!card) return {}; return parse(card); }, [card]);
  if (!card) return null;
}
```

### Always Wrap JSON.parse()

```typescript
// ✅ GOOD
const ctx = useMemo(() => {
  try {
    return typeof card.context === 'string'
      ? JSON.parse(card.context)
      : (card.context || {});
  } catch {
    console.warn('Failed to parse context:', card.id);
    return {};
  }
}, [card]);
```

### Set for Multi-Select Lookups

```typescript
// ✅ O(1) lookup
const [selected, setSelected] = useState<Set<string>>(new Set());
const isSelected = selected.has(id);

// ❌ O(n) lookup
const [selected, setSelected] = useState<string[]>([]);
const isSelected = selected.includes(id);
```

---

## TypeScript Patterns

- Use `unknown` + type guards instead of `any`
- Explicit return types on complex functions
- Optional chaining: `card?.context?.title || 'Untitled'`
- Avoid silent failures — log warnings, show toasts for user-visible errors

```typescript
// Correct return type + safe access
function parseContext(card: Card): Record<string, unknown> {
  try { return JSON.parse(card.context); }
  catch { return {}; }
}
```

---

## UI/UX Conventions

### Toast Notifications

Use `sonner` (primary). `react-hot-toast` is legacy — migrate when touching.

```typescript
import { toast } from 'sonner';
// ✅ Use for: API failures, successful operations, user-triggered errors
// ❌ Don't use for: background ops, validation errors (show inline)
```

### Card Hover State Transfer

When cards are deleted, `CardGrid` transfers hover state to the next card at the same index via `forceHover` prop. `preventEditRef` (300ms) prevents accidental edit modal on successive deletes.

### Card Actions by Artifact State

| State | Available actions |
|-------|------------------|
| `new` | Delete (trash) |
| `unmodified` | Remove from workspace (arrow) + Archive (box) |
| `modified` | Revert changes (rotate) |
| `archived` | Restore (refresh) |

### Multi-File Upload

Files dropped create artifacts immediately (before upload starts). Progress stored in `artifact.context.upload` (removed on completion).

---

## Chat Architecture ("Ask anything")

The header "Ask anything" input creates a `vnd.agience.chat+json` artifact. The chat type is server-owned — the viewer and agentic turn logic live on the Aria MCP server and are delivered to the host as an MCP App (`ui://` resource + `run_chat_turn` tool). The platform does not ship a compiled-in chat viewer or a dedicated `/llm/chat` endpoint; chat goes through the same generic artifact dispatch path as any other type.

Flow:
1. User types → `createArtifact()` with `context.chat.messages = [{role:"user", ...}]`
2. Registry resolves the chat type → fetches Aria's `ui://` chat viewer → renders it through `McpAppHost`
3. The viewer (inside the iframe) calls Aria's `run_chat_turn` tool via the MCP Apps `tools/call` bridge → `POST /artifacts/{aria_id}/invoke` on the backend
4. Viewer displays reply, persists updated messages via `updateArtifact()`

---

## Testing

**Run gates (must pass before push):**
```bash
cd frontend
npm run lint
npm run test
```

**Rules:**
- Vitest + React Testing Library
- Prefer role/text queries over brittle DOM selectors
- Prefer interaction tests over snapshot tests
- Bugfixes start with a failing test
- Use fake timers for animations, debounces, real-timer dependencies
- Frontend tests for UI/UX behavior changes and regressions

---

## Build & Versioning

- **Dev server**: `npm run dev` (auto-runs `predev` script to stamp version)
- **Version source**: `build_info.json` at root — format `{"version": "X.Y.Z"}`
- **Version stamp script**: `.scripts/ensure_version.py` creates `src/facet/public/version.json`

---

## Key File Reference

| File | Purpose |
|------|---------|
| `src/api/api.ts` | Axios instance — auth interceptors, 401 handling |
| `src/context/workspace/WorkspaceProvider.tsx` | Artifact state management (single source of truth) |
| `src/registry/viewer-map.ts` | Maps MIME types to viewer components |
| `src/content-types/` | Platform-native MIME renderers (P12 — text, markdown, JSON, PDF, image, audio, video, `_record`, `_shared`). No `vnd.*` viewers. |
| `src/isolation/McpAppHost.tsx` | Sandboxed iframe host for server-owned `ui://` viewers (MCP Apps) |
| `src/auth/` | AuthProvider + OAuth flow |
