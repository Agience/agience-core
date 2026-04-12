import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/collections', () => ({
  getCollectionArtifactsBatchGlobal: vi.fn(),
}));

import { getCollectionArtifactsBatchGlobal } from '../../api/collections';
import { resolveSearchHitsToArtifacts } from '../resolveSearchHits';
import type { ArtifactResponse } from '../../api/types/artifact';

describe('resolveSearchHitsToArtifacts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('resolves hits by version_id via the unified collection batch API', async () => {
    vi.mocked(getCollectionArtifactsBatchGlobal).mockResolvedValue([
      {
        id: 'artifact-1',
        content: 'Content',
        context: '{}',
        state: 'committed',
      },
    ]);

    const artifacts = await resolveSearchHitsToArtifacts([
      {
        id: 'search-doc-1',
        score: 1,
        root_id: 'root-1',
        version_id: 'artifact-1',
        collection_id: 'col-1',
      },
    ]);

    expect(getCollectionArtifactsBatchGlobal).toHaveBeenCalledWith(['artifact-1']);
    expect(artifacts).toHaveLength(1);
    expect(artifacts[0]?.id).toBe('artifact-1');
  });

  it('resolves hits by root_id when version_id is not found', async () => {
    vi.mocked(getCollectionArtifactsBatchGlobal).mockResolvedValue([
      {
        id: 'collection-version-1',
        root_id: 'root-collection-1',
        content: 'Collection artifact',
        context: '{}',
        state: 'committed',
      },
    ]);

    const artifacts = await resolveSearchHitsToArtifacts([
      {
        id: 'search-doc-2',
        score: 1,
        root_id: 'root-collection-1',
        version_id: 'collection-version-1',
        collection_id: 'col-1',
      },
    ]);

    expect(getCollectionArtifactsBatchGlobal).toHaveBeenCalledWith(['collection-version-1']);
    expect(artifacts).toHaveLength(1);
    expect(artifacts[0]?.root_id).toBe('root-collection-1');
  });

  it('deduplicates when multiple hits share the same root_id', async () => {
    vi.mocked(getCollectionArtifactsBatchGlobal).mockResolvedValue([
      {
        id: 'artifact-draft',
        root_id: 'root-shared-1',
        content: 'Draft',
        context: '{}',
        state: 'draft',
      },
      {
        id: 'artifact-committed',
        root_id: 'root-shared-1',
        content: 'Committed',
        context: '{}',
        state: 'committed',
      },
    ]);

    const artifacts = await resolveSearchHitsToArtifacts([
      {
        id: 'search-doc-3',
        score: 1,
        root_id: 'root-shared-1',
        version_id: 'artifact-draft',
        collection_id: 'col-1',
      },
      {
        id: 'search-doc-4',
        score: 0.9,
        root_id: 'root-shared-1',
        version_id: 'artifact-committed',
        collection_id: 'col-1',
      },
    ]);

    expect(artifacts).toHaveLength(1);
    expect(artifacts[0]?.id).toBe('artifact-draft');
  });

  it('returns empty array for empty hits', async () => {
    const artifacts = await resolveSearchHitsToArtifacts([]);
    expect(artifacts).toEqual([]);
    expect(getCollectionArtifactsBatchGlobal).not.toHaveBeenCalled();
  });

  it('returns empty array when batch fetch fails', async () => {
    vi.mocked(getCollectionArtifactsBatchGlobal).mockRejectedValue(new Error('network error'));
    const artifacts = await resolveSearchHitsToArtifacts([
      { id: 's1', score: 1, root_id: 'r1', version_id: 'v1' },
    ]);
    expect(artifacts).toEqual([]);
  });

  it('keeps container rows so workspaces and collections remain searchable', async () => {
    const containerLikeRow = {
      id: 'workspace-1',
      name: 'Inbox',
      description: 'Seed inbox workspace',
      state: 'draft',
    } as unknown as ArtifactResponse;

    vi.mocked(getCollectionArtifactsBatchGlobal).mockResolvedValue([
      containerLikeRow,
      {
        id: 'artifact-2',
        root_id: 'root-2',
        collection_id: 'workspace-1',
        content: 'Welcome to Agience',
        context: '{}',
        state: 'committed',
      },
    ]);

    const artifacts = await resolveSearchHitsToArtifacts([
      { id: 's-workspace', score: 1, root_id: 'workspace-1', version_id: 'workspace-1' },
      { id: 's-artifact', score: 0.9, root_id: 'root-2', version_id: 'artifact-2', collection_id: 'workspace-1' },
    ]);

    expect(artifacts).toHaveLength(2);
    expect(artifacts.map((a) => a.id)).toEqual(['workspace-1', 'artifact-2']);
  });
});
