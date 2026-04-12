/**
 * content-types.ts — Unified content type registry
 *
 * All definition data flows from the `types/` directory tree (presentation.json files)
 * via the `virtual:content-types` Vite plugin. Only wiring — icon resolution and
 * viewer lazy imports — lives here.
 *
 * To add or change a type: edit its `types/<top>/<sub>/presentation.json`.
 * No code change needed; the dev server hot-reloads automatically.
 */
import type { IconType } from 'react-icons';
import type { ComponentType } from 'react';
import { contentTypeDefinitions, CONTENT_TYPE_FALLBACK } from 'virtual:content-types';
import type { ResolvedContentType, ResolvedFrontendImplementation } from 'virtual:content-types';
import type { Artifact } from '@/context/workspace/workspace.types';
import { resolveIcon } from './icon-map';
import { resolveViewer } from './viewer-map';

/**
 * View Modes & States
 *
 * Content types declare which modes and states they support.
 * Common modes: 'floating', 'preview', 'inline', 'tree', 'grid', 'list'
 */
export type ViewMode = string;
export type ViewState = string;

/**
 * A single action an artifact context menu or hover bar can offer.
 * Content types declare their actions in `presentation.json`; this
 * interface is the hydrated runtime form.
 */
export interface ContentTypeAction {
  /** Stable identifier used by action handlers (e.g. "open", "delete", "archive"). */
  id: string;

  /** Display label shown in the context menu item. */
  label: string;

  /** Icon name string (resolved via icon-map at runtime). Omit for no icon. */
  icon?: string;

  /**
   * Artifact states in which this action is available.
   * Omit (or empty array) to show in all states.
   */
  states?: string[];

  /**
   * If true, show this action as a hover quick-action button on the artifact tile
   * (in addition to the context menu).
   */
  showInHover?: boolean;

  /** Marks the action as destructive — styled in red. */
  destructive?: boolean;
}

export interface ContentTypeFrontendImplementation {
  id: string;
  planes: string[];
  delivery: string;
  trust: string;
  priority: number;
  viewerKey?: string;
  providerKey?: string;
  bridge?: string;
  entry?: Record<string, unknown>;
  capabilities: string[];
  requiresEntitlements: string[];
  hostConstraints: string[];
}

/**
 * Content Type Definition — the hydrated runtime form used by all components.
 * icon and viewer are fully resolved (no more string refs at runtime).
 */
export interface ContentTypeDefinition {
  /** Stable identifier — from presentation.json `id` or derived from MIME. */
  id: string;

  /** Content type for this definition (exact or wildcard like "text/*"). */
  content_type: string;

  /** Display name. */
  label: string;

  /** Resolved React-icons component. */
  icon: IconType;

  /** Color for the horizontal bar and icon (hex). */
  color: string;

  /** Tailwind badge CSS classes. Empty string = no badge shown. */
  badgeClassName: string;

  /** Extra tile CSS classes (e.g. ring for orders). */
  tileClassName: string;

  /** Supported view modes. */
  modes: ViewMode[];

  /** Supported view states. */
  states: ViewState[];

  /** Default mode when an artifact is opened. */
  defaultMode: ViewMode;

  /** Default state when an artifact is opened. */
  defaultState: ViewState;

  /** Default depth for tree mode (containers only). */
  defaultDepth?: number;

  /** Maximum depth for tree mode (containers only). */
  maxDepth?: number;

  /**
   * Semantic container variant used by generic viewers to select a sub-component.
   * Replaces hardcoded `contentType.id` checks in Presentation (P6 compliance).
   * E.g. "resources" | "tools" | "prompts".
   */
  containerVariant?: string;

  /** Whether this is a container that can show children. */
  isContainer: boolean;

  /** Lazy viewer/editor component. */
  viewer?: () => Promise<{
    default: ComponentType<{
      artifact: Artifact;
      mode?: ViewMode;
      state?: ViewState;
      onOpenCollection?: (collectionId: string) => void;
      onOpenArtifact?: (artifact: Artifact) => void;
    }>;
  }>;

  /** Action to take when artifact is opened (e.g. "palette"). Undefined = default window. */
  openAction?: string;

  /** `ui://` resource URI for MCP Apps iframe viewer. When set, McpAppHost is used instead of compiled-in viewer. */
  resourceUri?: string;

  /** Server ID that owns the `ui://` resource. */
  resourceServer?: string;

  /** Whether users may create new artifacts of this type. */
  creatable: boolean;

  /** File extensions associated with this type. */
  extensions: string[];

  /** Optional frontend implementation manifest entries for future plane-aware resolution. */
  implementations: ContentTypeFrontendImplementation[];

  /**
   * Context-menu and hover-button actions for artifacts of this type.
   * When empty/absent, the host falls back to state-based defaults.
   */
  actions?: ContentTypeAction[];
}

function hydrateImplementation(
  raw: ResolvedFrontendImplementation,
): ContentTypeFrontendImplementation {
  return {
    id: raw.id,
    planes: raw.planes,
    delivery: raw.delivery,
    trust: raw.trust,
    priority: raw.priority,
    ...(raw.viewer_key ? { viewerKey: raw.viewer_key } : {}),
    ...(raw.provider_key ? { providerKey: raw.provider_key } : {}),
    ...(raw.bridge ? { bridge: raw.bridge } : {}),
    ...(raw.entry ? { entry: raw.entry } : {}),
    capabilities: raw.capabilities,
    requiresEntitlements: raw.requires_entitlements,
    hostConstraints: raw.host_constraints,
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// Hydration — convert raw virtual-module data into runtime ContentTypeDefinition
// ──────────────────────────────────────────────────────────────────────────────

function hydrateDefinition(raw: ResolvedContentType): ContentTypeDefinition {
  const viewerFactory = resolveViewer(raw.viewer);
  return {
    id: raw.id,
    content_type: raw.content_type,
    label: raw.label,
    icon: resolveIcon(raw.icon),
    color: raw.color,
    badgeClassName: raw.badge_class,
    tileClassName: raw.tile_class,
    modes: raw.modes,
    states: raw.states,
    defaultMode: raw.default_mode,
    defaultState: raw.default_state,
    ...(raw.default_depth != null ? { defaultDepth: raw.default_depth } : {}),
    ...(raw.max_depth != null ? { maxDepth: raw.max_depth } : {}),
    ...(raw.container_variant ? { containerVariant: raw.container_variant } : {}),
    isContainer: raw.is_container,
    ...(raw.open_action ? { openAction: raw.open_action } : {}),
    ...(raw.resource_uri ? { resourceUri: raw.resource_uri } : {}),
    ...(raw.resource_server ? { resourceServer: raw.resource_server } : {}),
    viewer: viewerFactory ?? undefined,
    creatable: raw.creatable,
    extensions: raw.extensions,
    implementations: raw.implementations.map(hydrateImplementation),
    // actions may be present in future presentation.json extensions
    ...((raw as unknown as { actions?: ContentTypeAction[] }).actions?.length
      ? { actions: (raw as unknown as { actions?: ContentTypeAction[] }).actions }
      : {}),
  };
}

/** All hydrated content type definitions, ordered: exact MIME types first, wildcards last. */
export const CONTENT_TYPES: ContentTypeDefinition[] = contentTypeDefinitions.map(hydrateDefinition);

/** Ultimate fallback used when no type matches an artifact's MIME. */
const FALLBACK_TYPE: ContentTypeDefinition = hydrateDefinition(CONTENT_TYPE_FALLBACK);

// ──────────────────────────────────────────────────────────────────────────────
// MIME resolution
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Resolve the best ContentTypeDefinition for a given MIME string.
 *
 * Priority:
 *   1. Exact match (e.g. "text/markdown")
 *   2. Category wildcard (e.g. "text/*" for any "text/...")
 *   3. Application wildcard ("application/*") as catch-all binary file
 *   4. Global fallback
 */
function findForContentType(contentType: string): ContentTypeDefinition {
  const normalized = contentType.split(';')[0]?.trim().toLowerCase() ?? '';
  if (!normalized) return FALLBACK_TYPE;

  // 1. Exact match
  const exact = CONTENT_TYPES.find((t) => t.content_type === normalized);
  if (exact) return exact;

  // 2. Category wildcard
  const category = normalized.split('/')[0];
  const wildcard = CONTENT_TYPES.find((t) => t.content_type === `${category}/*`);
  if (wildcard) return wildcard;

  // 3. application/* as last-resort for non-matched binary formats
  if (category !== 'application') {
    const appFallback = CONTENT_TYPES.find((t) => t.content_type === 'application/*');
    if (appFallback) return appFallback;
  }

  return FALLBACK_TYPE;
}

// ──────────────────────────────────────────────────────────────────────────────
// Public API — same surface as before so all existing consumers continue to work
// ──────────────────────────────────────────────────────────────────────────────

/** Returns the ContentTypeDefinition for a given artifact using canonical top-level content_type. */
export function getContentType(artifact: Artifact): ContentTypeDefinition {
  if (artifact.content_type) return findForContentType(artifact.content_type);
  return FALLBACK_TYPE;
}

/** Returns the ContentTypeDefinition whose id or MIME matches the given value. */
export function getContentTypeById(id: string): ContentTypeDefinition | undefined {
  return CONTENT_TYPES.find((t) => t.id === id || t.content_type === id);
}

/** All container types (isContainer === true). */
export function getContainerTypes(): ContentTypeDefinition[] {
  return CONTENT_TYPES.filter((t) => t.isContainer);
}

/** All types that users can create (creatable === true). */
export function getCreatableTypes(): ContentTypeDefinition[] {
  return CONTENT_TYPES.filter((t) => t.creatable);
}

// ──────────────────────────────────────────────────────────────────────────────
// Implementation resolution (Registry V2, Stage 2)
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Resolve the best frontend implementation for a content type on a given
 * UX plane.
 *
 * Resolution order (per content-type-registry-v2.md):
 *   1. Gather candidate implementations from the content type.
 *   2. Filter by requested plane.
 *   3. Sort by priority (higher wins).
 *   4. Return the first compatible candidate, or null.
 *
 * When no implementation matches the requested plane, the caller should
 * fall back to the default bundled viewer path.
 */
export function resolveImplementation(
  contentType: ContentTypeDefinition,
  plane: string,
): ContentTypeFrontendImplementation | null {
  const candidates = contentType.implementations
    .filter((impl) => impl.planes.length === 0 || impl.planes.includes(plane))
    .sort((a, b) => b.priority - a.priority);

  return candidates[0] ?? null;
}
