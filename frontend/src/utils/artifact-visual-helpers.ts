// Artifact visual helpers: icons, colors, filters
// NOTE: This module is being deprecated in favor of the unified content type registry
// See: frontend/src/registry/content-types.ts
import { FiFile } from 'react-icons/fi';
import type { IconType } from 'react-icons';
import type { Artifact } from '@/context/workspace/workspace.types';
import { getContentType, getContentTypeById } from '@/registry/content-types';

type ArtifactContextDict = Record<string, unknown>;
type ArtifactProcessing = {
  status?: string;
  asset_status?: string;
  content_status?: string;
  index_status?: string;
};

const PROCESSING_LOCKED_ACTIONS = new Set(['archive', 'remove', 'revert', 'restore']);

function parseArtifactContext(artifact: Artifact): ArtifactContextDict {
  try {
    const parsed = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as ArtifactContextDict
      : {};
  } catch {
    return {};
  }
}

// Artifact type detection from content_type
export function getArtifactType(artifact: Artifact): string {
  const contentType = getContentType(artifact);
  return contentType.id;
}

// Get icon for artifact type
export function getArtifactIcon(artifactType: string): IconType {
  // Prefer the unified registry.
  return getContentTypeById(artifactType)?.icon ?? FiFile;
}

// Get color for artifact type (horizontal bar)
export function getArtifactColor(artifactType: string): string {
  // Prefer the unified registry.
  return getContentTypeById(artifactType)?.color ?? '#9ca3af';
}

export function getArtifactProcessing(artifact: Artifact): ArtifactProcessing | null {
  const context = parseArtifactContext(artifact);
  const processing = context.processing;
  if (!processing || typeof processing !== 'object' || Array.isArray(processing)) {
    return null;
  }
  return processing as ArtifactProcessing;
}

export function isArtifactProcessingPending(artifact: Artifact): boolean {
  const processing = getArtifactProcessing(artifact);
  if (!processing) return false;

  const status = processing.status || '';
  const assetStatus = processing.asset_status || '';
  const contentStatus = processing.content_status || '';

  if (status === 'failed' || assetStatus === 'failed') {
    return false;
  }

  return (
    status === 'pending_upload' ||
    status === 'pending_handler' ||
    assetStatus === 'uploading' ||
    assetStatus === 'pending_upload' ||
    contentStatus === 'pending_handler'
  );
}

export function isArtifactActionBlocked(artifact: Artifact, actionId: string): boolean {
  return PROCESSING_LOCKED_ACTIONS.has(actionId) && isArtifactProcessingPending(artifact);
}

// Check if state badge should be shown.
// committed = normal published state — no badge needed.
export function shouldShowStateBadge(state: string | undefined): boolean {
  return state === 'draft' || state === 'archived';
}

// Get friendly label for state badge
export function getStateBadgeLabel(state: string | undefined): string {
  switch (state) {
    case 'draft': return 'Draft';
    case 'archived': return 'Archived';
    default: return '';
  }
}
