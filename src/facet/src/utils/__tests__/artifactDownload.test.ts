import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/workspaces', () => ({
  getArtifactContentUrl: vi.fn(),
}));

vi.mock('@/api/collections', () => ({
  getCollectionArtifactContentUrl: vi.fn(),
}));

import { getCollectionArtifactContentUrl } from '@/api/collections';
import { getArtifactContentUrl } from '@/api/workspaces';
import { resolveArtifactContentUrl } from '@/utils/artifactDownload';

describe('artifactDownload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses workspace content URLs when workspace scope is available', async () => {
    vi.mocked(getArtifactContentUrl).mockResolvedValueOnce({ url: 'https://cdn.example/workspace', expires_in: 300 });

    const url = await resolveArtifactContentUrl({
      id: 'artifact-1',
      collection_id: 'ws-1',
      context: '{}',
      content: '',
      state: 'committed',
    });

    expect(getArtifactContentUrl).toHaveBeenCalledWith('ws-1', 'artifact-1');
    expect(getCollectionArtifactContentUrl).not.toHaveBeenCalled();
    expect(url).toBe('https://cdn.example/workspace');
  });

  it('uses collection content URLs when only collection scope is available', async () => {
    vi.mocked(getCollectionArtifactContentUrl).mockResolvedValueOnce({ url: 'https://cdn.example/collection', expires_in: 300 });

    const url = await resolveArtifactContentUrl({
      root_id: 'root-1',
      collection_id: 'collection-1',
      context: '{}',
      content: '',
      state: 'committed',
    });

    expect(getCollectionArtifactContentUrl).toHaveBeenCalledWith('collection-1', 'root-1');
    expect(getArtifactContentUrl).not.toHaveBeenCalled();
    expect(url).toBe('https://cdn.example/collection');
  });

  it('falls back to committed collection membership when collection_id is absent', async () => {
    vi.mocked(getCollectionArtifactContentUrl).mockResolvedValueOnce({ url: 'https://cdn.example/fallback', expires_in: 300 });

    const url = await resolveArtifactContentUrl({
      root_id: 'root-2',
      committed_collection_ids: ['collection-2'],
      context: '{}',
      content: '',
      state: 'committed',
    });

    expect(getCollectionArtifactContentUrl).toHaveBeenCalledWith('collection-2', 'root-2');
    expect(url).toBe('https://cdn.example/fallback');
  });
});