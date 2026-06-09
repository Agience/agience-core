/**
 * Shared workspace types used across the application.
 * These types were originally co-located with SidebarEnhanced
 * and are now extracted here for broader reuse.
 */

/** Describes the currently-active content source displayed in the workspace panel. */
export type ActiveSource =
  | { type: 'workspace'; id: string }
  | { type: 'collection'; id: string }
  | { type: 'mcp-server'; id: string }
  | null;
