/**
 * content-types-plugin.ts
 *
 * Vite plugin that reads the repo-root `types/` directory tree at dev/build time,
 * merges `type.json` + `presentation.json` with inheritance, and exposes the
 * resolved definitions as the virtual module `virtual:content-types`.
 *
 * HOT-RELOAD: any change inside `typesRoot` triggers an HMR full-reload so the
 * registry stays in sync without a server restart.
 *
 * EXTENDING: drop a new `types/<top>/<sub>/type.json` + `presentation.json` into
 * the repo (or via `AGIENCE_TYPES_PATHS`) and restart / save — no code changes needed.
 */

import type { Plugin } from 'vite';
import { readdirSync, readFileSync, existsSync, statSync } from 'fs';
import { join, resolve } from 'path';

// ──────────────────────────────────────────────────────────────
// Public types (re-exported via the virtual module + d.ts)
// ──────────────────────────────────────────────────────────────

export interface RawTypeJson {
  content_type?: string;
  version?: number;
  extensions?: string[];
  inherits?: string[];
  description?: string;
}

export interface RawPresentationJson {
  /** Optional stable identifier override. Derived from MIME if omitted. */
  id?: string;
  label?: string;
  icon?: string;
  color?: string;
  badge_class?: string;
  tile_class?: string;
  modes?: string[];
  states?: string[];
  default_mode?: string;
  default_state?: string;
  is_container?: boolean;
  creatable?: boolean;
  open_action?: string | null;
  /** `ui://` resource URI for MCP Apps iframe viewer. */
  resource_uri?: string | null;
  /** Server ID that owns this resource (for MCP client routing). */
  resource_server?: string | null;
  viewer?: string | null;
  provider?: string | null;
  default_depth?: number | null;
  max_depth?: number | null;
  /**
   * Semantic variant used by generic container viewers to select the right
   * sub-component (e.g. "resources" | "tools" | "prompts").
   * Replaces hardcoded contentType.id checks in Presentation layer (P6).
   */
  container_variant?: string | null;
}

export interface RawFrontendImplementation {
  id?: string;
  planes?: string[];
  delivery?: string;
  trust?: string;
  priority?: number;
  viewer_key?: string | null;
  provider_key?: string | null;
  bridge?: string | null;
  entry?: Record<string, unknown> | null;
  capabilities?: string[];
  requires_entitlements?: string[];
  host_constraints?: string[];
}

export interface RawFrontendJson {
  version?: number;
  implementations?: RawFrontendImplementation[];
}

export interface ResolvedFrontendImplementation {
  id: string;
  planes: string[];
  delivery: string;
  trust: string;
  priority: number;
  viewer_key: string | null;
  provider_key: string | null;
  bridge: string | null;
  entry: Record<string, unknown> | null;
  capabilities: string[];
  requires_entitlements: string[];
  host_constraints: string[];
}

export interface ResolvedContentType {
  /** Stable identifier — overridden via presentation.json `id`, otherwise derived from content type. */
  id: string;
  content_type: string;
  is_wildcard: boolean;
  /** e.g. "image" for "image/*" — used for fast category matching */
  wildcard_prefix: string | null;
  extensions: string[];
  description: string;
  // Presentation
  label: string;
  icon: string;
  color: string;
  badge_class: string;
  tile_class: string;
  modes: string[];
  states: string[];
  default_mode: string;
  default_state: string;
  is_container: boolean;
  creatable: boolean;
  /** Action to take when artifact is opened (e.g. "palette"). Null = default window. */
  open_action: string | null;
  /** `ui://` resource URI for MCP Apps iframe viewer. Null = use compiled-in viewer. */
  resource_uri: string | null;
  /** Server ID that owns the `ui://` resource. */
  resource_server: string | null;
  /** String key into the frontend VIEWER_MAP */
  viewer: string | null;
  /** String key into the frontend PROVIDER_MAP */
  provider: string | null;
  default_depth: number | null;
  max_depth: number | null;
  /** Semantic container variant for registry-driven sub-component selection (e.g. "resources"). */
  container_variant: string | null;
  frontend_version: number | null;
  implementations: ResolvedFrontendImplementation[];
}

type ScannedContentType = RawTypeJson & RawPresentationJson & {
  frontend_version?: number;
  implementations?: RawFrontendImplementation[];
};

// ──────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────

const VIRTUAL_ID = 'virtual:content-types';
const RESOLVED_ID = '\0virtual:content-types';

function safeReadJson<T>(filePath: string): T | null {
  try {
    if (!existsSync(filePath)) return null;
    return JSON.parse(readFileSync(filePath, 'utf-8')) as T;
  } catch {
    return null;
  }
}

/**
 * Walk the `types/` directory one level at a time:
 *   types/<top>/<sub>/  →  MIME `<top>/<sub>` (or from type.json)
 *   types/<top>/_wildcard/ → MIME `<top>/*`
 *
 * Returns a Map: contentType → merged (type.json + presentation.json) raw object.
 */
function scanTypesRoot(
  typesRoot: string,
): Map<string, ScannedContentType> {
  const map = new Map<string, ScannedContentType>();

  // Detect server name from path: .../servers/<name>/ui → "<name>"
  const serverMatch = typesRoot.replace(/\\/g, '/').match(/\/servers\/([^/]+)\/ui$/);
  const serverName = serverMatch?.[1] ?? null;

  let topEntries: string[];
  try {
    topEntries = readdirSync(typesRoot);
  } catch {
    return map;
  }

  for (const top of topEntries) {
    const topDir = join(typesRoot, top);
    if (!statSync(topDir).isDirectory()) continue;
    if (top.startsWith('.') || top === 'README.md') continue;

    let subEntries: string[];
    try {
      subEntries = readdirSync(topDir);
    } catch {
      continue;
    }

    for (const sub of subEntries) {
      const subDir = join(topDir, sub);
      if (!statSync(subDir).isDirectory()) continue;
      if (sub.startsWith('.')) continue;

      const typeJson = safeReadJson<RawTypeJson & { ui?: RawPresentationJson }>(join(subDir, 'type.json'));
      const frontendJson = safeReadJson<RawFrontendJson>(join(subDir, 'frontend.json'));

      if (!typeJson && !frontendJson) continue;

      // UI metadata lives inside type.json["ui"]
      const uiJson = typeJson?.ui;

      // Derive content type from type.json.content_type or from the folder path
      const folderContentType = sub === '_wildcard'
        ? `${top}/*`
        : `${top}/${sub}`;
      const contentType = (typeJson?.content_type ?? folderContentType).trim();

      // Strip the embedded "ui" key so it doesn't pollute the top-level spread
      if (typeJson?.ui) delete typeJson.ui;

      // Auto-derive resource_uri and resource_server when a server-owned
      // view.html exists and the fields aren't already set explicitly.
      let derivedResource: { resource_uri?: string; resource_server?: string } = {};
      if (serverName && existsSync(join(subDir, 'view.html'))) {
        const slug = contentType.replace(/^application\//, '').replace(/\+json$/, '');
        derivedResource = {
          resource_uri: `ui://${serverName}/${slug}.html`,
          resource_server: serverName,
        };
      }

      map.set(contentType, {
        ...(typeJson ?? {}),
        ...(uiJson ?? {}),
        ...derivedResource,
        ...(frontendJson
          ? {
              frontend_version: frontendJson.version,
              implementations: frontendJson.implementations,
            }
          : {}),
      });
    }
  }

  return map;
}

/** Merge inheritance: parent fields first, then own fields override. */
function resolveOne(
  contentType: string,
  raw: Map<string, ScannedContentType>,
  visited = new Set<string>(),
): Partial<ScannedContentType> {
  if (visited.has(contentType)) return {};
  visited.add(contentType);

  const own = raw.get(contentType);
  if (!own) return {};

  let merged: Partial<ScannedContentType> = {};
  for (const parentMime of own.inherits ?? []) {
    const parentMerged = resolveOne(parentMime, raw, new Set(visited));
    merged = { ...merged, ...parentMerged };
  }

  // Own fields override parents (skip nulls except viewer which can be null intentionally)
  for (const [k, v] of Object.entries(own)) {
    if (k === 'inherits') continue;
    if (v === undefined) continue;
    (merged as Record<string, unknown>)[k] = v;
  }
  return merged;
}

/** Derive a stable slug from a MIME string. */
function contentTypeToId(mime: string): string {
  if (mime === '*/*') return 'file';
  if (mime.endsWith('/*')) return mime.slice(0, -2);
  const vendorMatch = mime.match(/^\/application\/vnd\.agience\.([\w-]+?)(?:\+\w+)?$/) ||
    mime.match(/^application\/vnd\.agience\.([\w-]+?)(?:\+\w+)?$/);
  if (vendorMatch) return vendorMatch[1];
  return mime.replace('/', '-').replace(/[^a-z0-9-]/gi, '-').toLowerCase();
}

const FALLBACK: ResolvedContentType = {
  id: 'file',
  content_type: '*/*',
  is_wildcard: true,
  wildcard_prefix: null,
  extensions: [],
  description: 'Unknown file type',
  label: 'File',
  icon: 'file',
  color: '#9ca3af',
  badge_class: '',
  tile_class: '',
  modes: ['floating'],
  states: ['view'],
  default_mode: 'floating',
  default_state: 'view',
  is_container: false,
  creatable: false,
  open_action: null,
  resource_uri: null,
  resource_server: null,
  container_variant: null,
  viewer: null,
  provider: null,
  default_depth: null,
  max_depth: null,
  frontend_version: null,
  implementations: [],
};

function resolveFrontendImplementations(
  contentType: string,
  implementations: RawFrontendImplementation[] | undefined,
): ResolvedFrontendImplementation[] {
  return (implementations ?? []).map((implementation, index) => ({
    id: implementation.id ?? `${contentTypeToId(contentType)}-impl-${index + 1}`,
    planes: implementation.planes ?? [],
    delivery: implementation.delivery ?? 'bundled',
    trust: implementation.trust ?? 'first-party',
    priority: implementation.priority ?? 0,
    viewer_key: implementation.viewer_key ?? null,
    provider_key: implementation.provider_key ?? null,
    bridge: implementation.bridge ?? null,
    entry: implementation.entry ?? null,
    capabilities: implementation.capabilities ?? [],
    requires_entitlements: implementation.requires_entitlements ?? [],
    host_constraints: implementation.host_constraints ?? [],
  }));
}

function buildDefinitions(typesRoots: string[]): ResolvedContentType[] {
  const raw = new Map<string, ScannedContentType>();

  for (const typesRoot of typesRoots) {
    const scanned = scanTypesRoot(typesRoot);
    for (const [contentType, definition] of scanned.entries()) {
      if (!raw.has(contentType)) {
        raw.set(contentType, definition);
      } else if (definition.resource_uri) {
        // A server-owned root is adding a ui:// viewer (view.html) for a type
        // already declared in the base types/ directory. Merge resource_uri and
        // resource_server from the server entry so McpAppHost is used instead of
        // the compiled-in viewer fallback.
        const existing = raw.get(contentType)!;
        raw.set(contentType, {
          ...existing,
          resource_uri: definition.resource_uri,
          resource_server: definition.resource_server ?? existing.resource_server,
        });
      }
    }
  }

  const results: ResolvedContentType[] = [];

  for (const contentType of raw.keys()) {
    const m = resolveOne(contentType, raw);
    const isWildcard = contentType.endsWith('/*');
    const prefix = isWildcard ? contentType.slice(0, -2) : null;

    const idOverride = (m.id as string | undefined) ?? undefined;
    results.push({
      id: idOverride ?? contentTypeToId(contentType),
      content_type: contentType,
      is_wildcard: isWildcard,
      wildcard_prefix: prefix,
      extensions: (m.extensions as string[]) ?? [],
      description: (m.description as string) ?? '',
      label: (m.label as string) ?? contentType,
      icon: (m.icon as string) ?? 'file',
      color: (m.color as string) ?? '#9ca3af',
      badge_class: (m.badge_class as string) ?? '',
      tile_class: (m.tile_class as string) ?? '',
      modes: (m.modes as string[]) ?? ['floating'],
      states: (m.states as string[]) ?? ['view'],
      default_mode: (m.default_mode as string) ?? 'floating',
      default_state: (m.default_state as string) ?? 'view',
      is_container: Boolean(m.is_container),
      creatable: Boolean(m.creatable),
      open_action: (m.open_action as string | null | undefined) ?? null,
      resource_uri: (m.resource_uri as string | null | undefined) ?? null,
      resource_server: (m.resource_server as string | null | undefined) ?? null,
      viewer: (m.viewer as string | null | undefined) ?? null,
      provider: (m.provider as string | null | undefined) ?? null,
      default_depth: (m.default_depth as number | null | undefined) ?? null,
      max_depth: (m.max_depth as number | null | undefined) ?? null,
      container_variant: (m.container_variant as string | null | undefined) ?? null,
      frontend_version: (m.frontend_version as number | null | undefined) ?? null,
      implementations: resolveFrontendImplementations(
        contentType,
        m.implementations as RawFrontendImplementation[] | undefined,
      ),
    });
  }

  // Sort: exact content types before wildcards (exact first for matching priority)
  results.sort((a, b) => {
    if (a.is_wildcard !== b.is_wildcard) return a.is_wildcard ? 1 : -1;
    return a.content_type.localeCompare(b.content_type);
  });

  return results;
}

// ──────────────────────────────────────────────────────────────
// Plugin factory
// ──────────────────────────────────────────────────────────────

export function contentTypesPlugin(typesRoots: string | string[]): Plugin {
  const absRoots = (Array.isArray(typesRoots) ? typesRoots : [typesRoots]).map((root) => resolve(root));
  let definitions: ResolvedContentType[] = [];

  function reload() {
    definitions = buildDefinitions(absRoots);
  }

  return {
    name: 'vite-plugin-content-types',

    buildStart() {
      // Skip eager scan in test mode; definitions lazy-load on first import.
      if (!process.env.VITEST) reload();
    },

    resolveId(id) {
      if (id === VIRTUAL_ID) return RESOLVED_ID;
    },

    load(id) {
      if (id !== RESOLVED_ID) return;
      // Lazy-load: in test mode buildStart is skipped, so scan on first access.
      if (definitions.length === 0) reload();
      return [
        `export const contentTypeDefinitions = ${JSON.stringify(definitions, null, 2)};`,
        `export const CONTENT_TYPE_FALLBACK = ${JSON.stringify(FALLBACK, null, 2)};`,
      ].join('\n');
    },

    configureServer(server) {
      // Watch all configured types roots for HMR.
      for (const absRoot of absRoots) {
        server.watcher.add(absRoot);
      }
      server.watcher.on('change', (file) => {
        if (!absRoots.some((absRoot) => file.startsWith(absRoot))) return;
        reload();
        const mod = server.moduleGraph.getModuleById(RESOLVED_ID);
        if (mod) server.moduleGraph.invalidateModule(mod);
        server.hot.send({ type: 'full-reload' });
      });
      server.watcher.on('add', (file) => {
        if (!absRoots.some((absRoot) => file.startsWith(absRoot))) return;
        reload();
        const mod = server.moduleGraph.getModuleById(RESOLVED_ID);
        if (mod) server.moduleGraph.invalidateModule(mod);
        server.hot.send({ type: 'full-reload' });
      });
    },
  };
}
