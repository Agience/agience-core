// src/utils/desktop-layout.ts
/**
 * Desktop layout utilities: position storage, reading order projection, and layout helpers.
 */

export type LayoutMode = 'flow' | 'desktop';

export interface ArtifactPosition {
  x: number;
  y: number;
  w?: number;
  h?: number;
  z?: number;
  minimized?: boolean;
}

export interface DesktopLayout {
  mode: LayoutMode;
  positions: Record<string, ArtifactPosition>; // artifactId -> position
  gridSize?: number; // snap grid size (e.g., 16px, 32px)
  snapToGrid?: boolean;
}

const STORAGE_KEY_PREFIX = 'agience:workspace-layout:';

/**
 * Load desktop layout from localStorage for a given workspace.
 */
export function loadDesktopLayout(workspaceId: string): DesktopLayout | null {
  try {
    const key = `${STORAGE_KEY_PREFIX}${workspaceId}`;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as DesktopLayout;
  } catch (err) {
    console.error('Failed to load desktop layout:', err);
    return null;
  }
}

/**
 * Save desktop layout to localStorage for a given workspace.
 */
export function saveDesktopLayout(workspaceId: string, layout: DesktopLayout): void {
  try {
    const key = `${STORAGE_KEY_PREFIX}${workspaceId}`;
    localStorage.setItem(key, JSON.stringify(layout));
  } catch (err) {
    console.error('Failed to save desktop layout:', err);
  }
}

/**
 * Update a single artifact's position in the desktop layout.
 */
export function updateArtifactPosition(
  workspaceId: string,
  artifactId: string,
  position: ArtifactPosition
): void {
  const layout = loadDesktopLayout(workspaceId) || {
    mode: 'desktop',
    positions: {},
  };
  layout.positions[artifactId] = position;
  saveDesktopLayout(workspaceId, layout);
}

/**
 * Compute desktop reading order (L→R, T→B with row coalescing).
 * Returns artifact IDs sorted by (row, x, artifactId).
 */
export function getDesktopReadingOrder(
  artifactIds: string[],
  layoutById: Record<string, ArtifactPosition>,
  rowSnap: number = 180 // default to artifact height (adjust based on actual artifact size)
): string[] {
  const items = artifactIds.map((id) => {
    const pos = layoutById[id];
    if (!pos) return { id, row: 0, x: 0 }; // fallback for artifacts without position
    const row = Math.round(pos.y / rowSnap);
    return { id, row, x: pos.x };
  });

  items.sort((a, b) => {
    if (a.row !== b.row) return a.row - b.row;
    if (a.x !== b.x) return a.x - b.x;
    return a.id.localeCompare(b.id);
  });

  return items.map((item) => item.id);
}

/**
 * Snap position to grid if enabled.
 */
export function snapToGrid(pos: { x: number; y: number }, gridSize: number): { x: number; y: number } {
  return {
    x: Math.round(pos.x / gridSize) * gridSize,
    y: Math.round(pos.y / gridSize) * gridSize,
  };
}

/**
 * Get default position for a new artifact (bottom-right of existing artifacts, or origin).
 */
export function getDefaultArtifactPosition(
  existingPositions: Record<string, ArtifactPosition>,
  artifactWidth: number = 180,
  gridSize: number = 16
): ArtifactPosition {
  const positions = Object.values(existingPositions);
  if (positions.length === 0) {
    // First artifact: start at grid origin
    return { x: gridSize, y: gridSize };
  }

  // Find rightmost edge of existing artifacts
  const maxX = Math.max(...positions.map((p) => p.x + (p.w || artifactWidth)));

  // Place new artifact at bottom-right with some spacing
  return {
    x: Math.max(gridSize, maxX + gridSize),
    y: gridSize,
  };
}
