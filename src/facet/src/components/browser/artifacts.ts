import type { Artifact } from '@/context/workspace/workspace.types';
import type { ActiveSource } from '@/types/workspace';

export function deriveArtifactCountArtifacts({
  searchFilteredArtifacts,
  resolvedDisplayArtifacts,
  isShowingSearchResults,
}: {
  searchFilteredArtifacts: Artifact[];
  resolvedDisplayArtifacts: Artifact[];
  isShowingSearchResults: boolean;
  activeSourceType?: Exclude<ActiveSource, null>['type'];
}): Artifact[] {
  return isShowingSearchResults ? resolvedDisplayArtifacts : searchFilteredArtifacts;
}