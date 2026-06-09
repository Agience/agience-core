/**
 * resolveSearchHits.ts
 *
 * Converts a SearchResponse's hits into full Artifact objects by batch-fetching
 * from the artifact store. Workspaces and collections are the same store, so
 * all hits are resolved via a single batch-global call.
 *
 * Results are returned in the original hit order (preserving search ranking).
 */
import type { SearchHit } from '../api/types/search';
import type { Artifact } from '../context/workspace/workspace.types';
import { getCollectionArtifactsBatchGlobal } from '../api/collections';

/**
 * Convert an array of SearchHits to fully populated Artifact objects.
 */
export async function resolveSearchHitsToArtifacts(hits: SearchHit[]): Promise<Artifact[]> {
  if (!hits || hits.length === 0) return [];

  // All hits live in the unified artifact store — workspaces are collections.
  const versionIds = [...new Set(hits.map((h) => h.version_id))];

  let artifacts: Artifact[] = [];
  try {
    artifacts = await getCollectionArtifactsBatchGlobal(versionIds);
  } catch (err) {
    console.error('[Search] Failed to batch-fetch artifacts:', err);
    return [];
  }

  const byRootId = new Map<string, Artifact>();
  const byVersionId = new Map<string, Artifact>();
  artifacts.forEach((artifact) => {
    if (artifact.root_id) byRootId.set(String(artifact.root_id), artifact);
    if (artifact.id) byVersionId.set(String(artifact.id), artifact);
  });

  // Reassemble in hit order, deduplicating by root_id
  const result: Artifact[] = [];
  const seen = new Set<string>();
  for (const hit of hits) {
    const logicalRootId = String(hit.root_id || hit.version_id);
    if (seen.has(logicalRootId)) continue;

    const artifact =
      byVersionId.get(hit.version_id) ||
      byRootId.get(hit.root_id);

    if (artifact) {
      result.push(artifact);
      seen.add(logicalRootId);
    }
  }

  return result;
}
