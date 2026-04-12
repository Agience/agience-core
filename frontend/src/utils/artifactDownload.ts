import { getCollectionArtifactContentUrl } from '@/api/collections';
import { getArtifactContentUrl } from '@/api/workspaces';
import type { Artifact } from '@/context/workspace/workspace.types';

/** Returns true when the artifact's content is stored in S3/MinIO (not inline). */
export function isS3Stored(context: Record<string, unknown>): boolean {
  if (context.content_key) return true;
  const storage = context.storage as Record<string, unknown> | undefined;
  return storage?.mode === 'minio-only' || storage?.mode === 's3';
}

export function needsSignedContentUrl(contentType?: string): boolean {
  return Boolean(
    contentType && (contentType === 'application/pdf' || contentType.startsWith('image/') || contentType.startsWith('audio/') || contentType.startsWith('video/'))
  );
}

/** Returns true when we need to fetch a signed content URL — the artifact content lives in S3. */
export function needsContentUrl(_contentType: string | undefined, context: Record<string, unknown>): boolean {
  return isS3Stored(context);
}

export async function resolveArtifactContentUrl(artifact: Artifact, activeWorkspaceId?: string): Promise<string | undefined> {
  const workspaceId = artifact.collection_id || activeWorkspaceId || undefined;
  if (workspaceId && artifact.id) {
    const response = await getArtifactContentUrl(workspaceId, String(artifact.id));
    return response.url;
  }

  const collectionId = artifact.collection_id || artifact.committed_collection_ids?.[0];
  if (collectionId && artifact.root_id) {
    const response = await getCollectionArtifactContentUrl(String(collectionId), String(artifact.root_id));
    return response.url;
  }

  return undefined;
}