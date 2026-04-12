import { describe, expect, it } from 'vitest';
import type { ArtifactResponse } from '@/api/types/artifact';

import { deriveArtifactCountArtifacts } from '@/components/browser/artifacts';

describe('deriveArtifactCountArtifacts', () => {
  it('returns searchFilteredArtifacts when not showing search results', () => {
    const sourceArtifacts: ArtifactResponse[] = [
      { id: 'source-1', context: '{}', content: '', state: 'committed' },
      { id: 'artifact-1', context: '{}', content: '', state: 'committed' },
    ];

    const result = deriveArtifactCountArtifacts({
      searchFilteredArtifacts: sourceArtifacts,
      resolvedDisplayArtifacts: [],
      isShowingSearchResults: false,
    });

    expect(result.map((artifact) => artifact.id)).toEqual(['source-1', 'artifact-1']);
  });

  it('returns resolvedDisplayArtifacts when showing search results', () => {
    const searchArtifacts: ArtifactResponse[] = [
      { id: 'hit-1', context: '{}', content: '', state: 'committed' },
    ];

    const result = deriveArtifactCountArtifacts({
      searchFilteredArtifacts: [],
      resolvedDisplayArtifacts: searchArtifacts,
      isShowingSearchResults: true,
    });

    expect(result.map((artifact) => artifact.id)).toEqual(['hit-1']);
  });
});