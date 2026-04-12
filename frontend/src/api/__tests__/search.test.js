import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => {
  return {
    default: {
      post: vi.fn(),
    },
  };
});

import api from '../api';
import { searchGlobal, searchWorkspace, searchCollection, getWorkspaceSuggestions, getCollectionSuggestions } from '../search';

const mkUnified = (overrides = {}) => ({
  hits: [
    { id: 'h1', score: 1.23, root_id: 'r1', version_id: 'v1', workspace_id: 'w1' },
    { id: 'h2', score: 0.5, root_id: 'r2', version_id: 'v2', collection_id: 'c1' },
  ],
  total: 2,
  query_text: 'foo',
  used_hybrid: true,
  from: 0,
  size: 20,
  ...overrides,
});

describe('api/search (unified /search)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('searchGlobal posts minimal body and maps response', async () => {
    api.post.mockResolvedValueOnce({ data: mkUnified() });
    const res = await searchGlobal({ query_text: 'foo' });
    expect(api.post).toHaveBeenCalledWith(
      '/artifacts/search',
      expect.objectContaining({
        query_text: 'foo',
        from: 0,
        size: 20,
        sort: 'relevance',
        highlight: true,
      })
    );
    expect(res.total).toBe(2);
    expect(res.hits[0]).toEqual(expect.objectContaining({ id: 'h1', root_id: 'r1', version_id: 'v1' }));
  });

  it('searchWorkspace adds scope', async () => {
    api.post.mockResolvedValueOnce({ data: mkUnified() });
    await searchWorkspace({ query_text: 'bar', collection_id: 'w1' });
    const [, body] = api.post.mock.calls[0];
    expect(body.scope).toEqual(['w1']);
    expect(body.source_types).toBeUndefined();
  });

  it('searchCollection adds scope', async () => {
    api.post.mockResolvedValueOnce({ data: mkUnified() });
    await searchCollection({ query_text: 'baz', collection_id: 'c1' });
    const [, body] = api.post.mock.calls[0];
    expect(body.scope).toEqual(['c1']);
    expect(body.source_types).toBeUndefined();
  });

  it('mapUnifiedResponse defaults gracefully when backend returns null/undefined data', async () => {
    api.post.mockResolvedValueOnce({ data: null });
    const res = await searchGlobal({ query_text: 'empty' });
    expect(res.hits).toEqual([]);
    expect(res.total).toBe(0);
    expect(res.used_hybrid).toBe(false);
  });

  describe('getWorkspaceSuggestions', () => {
    it('returns empty tags and titles without making an API call', async () => {
      const res = await getWorkspaceSuggestions({ query_text: 'art', workspace_id: 'ws-1' });
      expect(res).toEqual({ tags: [], titles: [] });
      expect(api.post).not.toHaveBeenCalled();
    });
  });

  describe('getCollectionSuggestions', () => {
    it('returns empty tags and titles without making an API call', async () => {
      const res = await getCollectionSuggestions({ query_text: 'doc', collection_id: 'c-1' });
      expect(res).toEqual({ tags: [], titles: [] });
      expect(api.post).not.toHaveBeenCalled();
    });
  });
});
