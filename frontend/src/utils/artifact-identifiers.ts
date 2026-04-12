import type { Artifact } from '@/context/workspace/workspace.types';

export const getStableArtifactId = (artifact: Artifact): string | null => {
  if (artifact.id != null) {
    const value = String(artifact.id).trim();
    if (value) return value;
  }
  if (artifact.root_id != null) {
    const value = String(artifact.root_id).trim();
    if (value) return value;
  }
  return null;
};
