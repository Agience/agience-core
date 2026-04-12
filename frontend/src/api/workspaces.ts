// frontend/src/api/workspaces.ts

import { get, post, patch, del } from './api';
import { WORKSPACE_CONTENT_TYPE } from '@/utils/content-type';
import { subscribeEvents, type BusEvent } from './events';
import {
  WorkspaceResponse,
  WorkspaceCreate,
  WorkspaceUpdate,
} from './types/workspace';
import { ArtifactResponse, ArtifactCreate, ArtifactUpdate } from './types/artifact';
import {
  type WorkspaceCommitRequest,
  type WorkspaceCommitResponse,
} from './types/workspace_commit';
import type { ArtifactKeyResponse } from './types/workspace_card';

// list all workspaces
export function listWorkspaces(): Promise<WorkspaceResponse[]> {
  return get('/artifacts/containers?type=workspace');
}

// get one workspace
export function getWorkspace(id: string): Promise<WorkspaceResponse> {
  return get(`/artifacts/${id}`);
}

// create new workspace
export function createWorkspace(
  input: WorkspaceCreate
): Promise<WorkspaceResponse> {
  return post('/artifacts', { ...input, content_type: WORKSPACE_CONTENT_TYPE });
}

// update name/description
export function updateWorkspace(
  id: string,
  input: WorkspaceUpdate
): Promise<WorkspaceResponse> {
  return patch(`/artifacts/${id}`, input);
}

// delete workspace
export function deleteWorkspace(id: string): Promise<void> {
  return del(`/artifacts/${id}`);
}

// list artifacts in workspace
export async function listWorkspaceArtifacts(
  workspaceId: string
): Promise<{ items: ArtifactResponse[]; order_version?: number }> {
  const res = await get(`/artifacts/list?container_id=${encodeURIComponent(workspaceId)}`) as ArtifactResponse[] | { items: ArtifactResponse[]; order_version?: number };
  return Array.isArray(res) ? { items: res } : res;
}

// add an artifact
export function addArtifactToWorkspace(
  workspaceId: string,
  input: ArtifactCreate
): Promise<ArtifactResponse> {
  return post('/artifacts', { container_id: workspaceId, ...input });
}

// Import a collection artifact (by root_id) into a workspace — links, does not copy
export function importCollectionArtifactToWorkspace(
  workspaceId: string,
  rootId: string
): Promise<ArtifactResponse> {
  return post(`/artifacts`, { container_id: workspaceId, source_artifact_id: rootId });
}

// update an artifact
export function updateWorkspaceArtifact(
  _workspaceId: string,
  artifactId: string,
  input: ArtifactUpdate
): Promise<ArtifactResponse> {
  return patch(`/artifacts/${artifactId}`, input);
}

// delete an artifact
export function deleteWorkspaceArtifact(
  _workspaceId: string,
  artifactId: string
): Promise<void> {
  return del(`/artifacts/${artifactId}`);
}

export function removeWorkspaceArtifact(
  workspaceId: string,
  artifactId: string,
): Promise<void> {
  return post(`/artifacts/${artifactId}/remove`, { container_id: workspaceId });
}

// batch fetch artifacts across all accessible workspaces
export async function getWorkspaceArtifactsBatchGlobal(
  artifactIds: string[]
): Promise<ArtifactResponse[]> {
  const res = await post<{ artifacts: ArtifactResponse[] }>('/artifacts/batch', { artifact_ids: artifactIds });
  return res.artifacts ?? [];
}

export async function revertWorkspaceArtifact(
  _workspaceId: string,
  artifactId: string
): Promise<ArtifactResponse> {
  return post(`/artifacts/${artifactId}/revert`, {});
}

// move artifact between workspaces
export async function moveArtifactToWorkspace(
  _sourceWorkspaceId: string,
  artifactId: string,
  targetWorkspaceId: string
): Promise<ArtifactResponse> {
  return post(`/artifacts/${artifactId}/move`, { target_container_id: targetWorkspaceId });
}

export async function commitWorkspace(
  workspaceId: string,
  input?: WorkspaceCommitRequest
): Promise<WorkspaceCommitResponse> {
  return post(`/artifacts/${workspaceId}/commit`, input);
}

export async function previewWorkspaceCommit(
  workspaceId: string,
  input?: WorkspaceCommitRequest
): Promise<WorkspaceCommitResponse> {
  return post(`/artifacts/${workspaceId}/commit/preview`, input);
}

// find artifacts similar to a freeform text input
export function findSimilarText(
  input: string
): Promise<ArtifactResponse[]> {
  // TODO: Map to /artifacts/search when similarity search is available
  return post('/artifacts/search', { query_text: input });
}

// find artifacts similar to a given artifact in the same workspace
export function findSimilarArtifact(
  artifactId: string
): Promise<ArtifactResponse[]> {
  // TODO: Map to /artifacts/search with artifact-based similarity
  return post('/artifacts/search', { query_text: artifactId });
}

export async function orderWorkspaceArtifacts(
  workspaceId: string,
  orderedIds: string[],
  version?: number
): Promise<{ ok: boolean; version: number }> {
  const result = await patch<{ order_version: number }>(`/artifacts/${workspaceId}/order`, {
    ordered_ids: orderedIds,
    ...(version !== undefined ? { order_version: version } : {}),
  });
  return { ok: true, version: result.order_version };
}

// Upload operations
import type {
  UploadInitiateRequest,
  UploadInitiateResponse,
  UploadStatusUpdateRequest,
} from './types/upload';

export function initiateUpload(
  workspaceId: string,
  input: UploadInitiateRequest
): Promise<UploadInitiateResponse> {
  return post(`/artifacts/${workspaceId}/upload-initiate`, input);
}

export function updateUploadStatus(
  _workspaceId: string,
  uploadId: string,
  input: UploadStatusUpdateRequest
): Promise<ArtifactResponse> {
  return patch(`/artifacts/${uploadId}/upload-status`, input);
}

// Get presigned URL for a specific part in multipart upload
export function getMultipartPartUrl(
  _workspaceId: string,
  uploadId: string,
  partNumber: number
): Promise<{ url: string; part_number: number }> {
  return get(`/artifacts/${uploadId}/multipart-part-url?part_number=${partNumber}`);
}

// Get signed content URL for an artifact's file
export function getArtifactContentUrl(
  _workspaceId: string,
  artifactId: string,
): Promise<{ url: string; expires_in: number | null; filename?: string }> {
  return get(`/artifacts/${artifactId}/content-url`);
}

// Artifact-scoped key rotation
/** Generate or rotate an artifact-scoped API key. Shown once — save immediately. */
export function rotateArtifactKey(
  _workspaceId: string,
  artifactId: string,
  keyContext: string,
): Promise<ArtifactKeyResponse> {
  // TODO: Map to unified artifact key endpoint when available
  return post(`/artifacts/${artifactId}/key?key_context=${encodeURIComponent(keyContext)}`, {});
}

// === Workspace Change Events (SSE) ===

export type InvokeEventPayload = {
  artifact_id?: string;
  container_id?: string;
  content_type?: string;
  op?: string;
  phase?: string;
  actor_id?: string;
  ts?: number;
  result?: unknown;
  error?: { type: string; message: string };
};

export type WorkspaceEventHandlers = {
  onArtifactCreated?: (artifact: ArtifactResponse) => void;
  onArtifactUpdated?: (artifact: ArtifactResponse) => void;
  onArtifactDeleted?: (artifactId: string) => void;
  onUploadComplete?: (artifact: ArtifactResponse) => void;
  onWorkspaceRefreshed?: () => void;
  // Operation lifecycle events (Phase 1 — Enterprise Eventing refactor).
  // Fired by the operation dispatcher emit envelope around every invoke.
  onInvokeStarted?: (payload: InvokeEventPayload) => void;
  onInvokeCompleted?: (payload: InvokeEventPayload) => void;
  onInvokeFailed?: (payload: InvokeEventPayload) => void;
};

/**
 * Subscribe to real-time workspace change events via the unified /events
 * WebSocket. Thin adapter over `subscribeEvents` in api/events.ts that
 * translates `BusEvent` messages into the legacy handler-callback shape.
 *
 * Returns a cleanup function — call it to tear down the subscription (use
 * as a useEffect return value).
 */
export function subscribeWorkspaceEvents(
  workspaceId: string,
  handlers: WorkspaceEventHandlers,
): () => void {
  return subscribeEvents(
    {
      container_id: workspaceId,
      event_names: [
        'artifact.created',
        'artifact.updated',
        'artifact.deleted',
        'upload.complete',
        'workspace.refreshed',
        'artifact.invoke.started',
        'artifact.invoke.completed',
        'artifact.invoke.failed',
      ],
    },
    (evt: BusEvent) => {
      const payload = evt.payload || {};
      switch (evt.event) {
        case 'artifact.created': {
          const a = (payload as { artifact?: ArtifactResponse }).artifact;
          if (a) handlers.onArtifactCreated?.(a);
          return;
        }
        case 'artifact.updated': {
          const a = (payload as { artifact?: ArtifactResponse }).artifact;
          if (a) handlers.onArtifactUpdated?.(a);
          return;
        }
        case 'artifact.deleted': {
          const id = (payload as { artifact_id?: string }).artifact_id;
          if (id) handlers.onArtifactDeleted?.(id);
          return;
        }
        case 'upload.complete': {
          const a = (payload as { artifact?: ArtifactResponse }).artifact;
          if (a) {
            handlers.onUploadComplete?.(a);
            handlers.onArtifactUpdated?.(a);
          }
          return;
        }
        case 'workspace.refreshed':
          handlers.onWorkspaceRefreshed?.();
          return;
        case 'artifact.invoke.started':
          handlers.onInvokeStarted?.(payload as unknown as InvokeEventPayload);
          return;
        case 'artifact.invoke.completed':
          handlers.onInvokeCompleted?.(payload as unknown as InvokeEventPayload);
          return;
        case 'artifact.invoke.failed':
          handlers.onInvokeFailed?.(payload as unknown as InvokeEventPayload);
          return;
      }
    },
  );
}
