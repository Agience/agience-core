import type { Artifact } from '@/context/workspace/workspace.types';
import type { Collection } from '@/context/collections/collection.types';
import { safeParseArtifactContext } from '@/utils/artifactContext';
import { COLLECTION_CONTENT_TYPE } from '@/utils/content-type';

function addLabel(map: Map<string, string>, id: unknown, label: unknown) {
  if (typeof id !== 'string' || !id.trim()) return;
  if (typeof label !== 'string' || !label.trim()) return;
  if (!map.has(id)) {
    map.set(id, label.trim());
  }
}

export function buildCollectionLabelMap(
  artifacts: Artifact[],
  collections: Collection[] = [],
): Map<string, string> {
  const labels = new Map<string, string>();

  for (const artifact of artifacts) {
    const context = safeParseArtifactContext(artifact.context);
    const contentType = context.content_type;
    if (contentType !== COLLECTION_CONTENT_TYPE) continue;

    const title =
      (typeof context.title === 'string' && context.title.trim()) ||
      (typeof context.name === 'string' && context.name.trim()) ||
      undefined;

    addLabel(labels, artifact.id, title);
    addLabel(labels, artifact.root_id, title);
    addLabel(labels, context.collection_id, title);
    addLabel(labels, context.collectionId, title);
    addLabel(labels, context.target_collection_id, title);

    const target = context.target;
    if (target && typeof target === 'object') {
      addLabel(labels, (target as { id?: unknown }).id, title);
      addLabel(labels, (target as { collection_id?: unknown }).collection_id, title);
    }

    const viewTarget = context.view?.target;
    if (viewTarget && typeof viewTarget === 'object') {
      addLabel(labels, (viewTarget as { id?: unknown }).id, title);
      addLabel(labels, (viewTarget as { collection_id?: unknown }).collection_id, title);
    }
  }

  for (const collection of collections) {
    addLabel(labels, collection.id, collection.name);
  }

  return labels;
}

export function resolveCollectionLabel(
  collectionId: string,
  labelMap: Map<string, string>,
): string {
  return labelMap.get(collectionId) || `Collection ${collectionId}`;
}