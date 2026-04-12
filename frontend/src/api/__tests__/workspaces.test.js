import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    put: vi.fn(),
  };
});

import { get, post, patch } from '../api';
import {
  listWorkspaces,
  createWorkspace,
  listWorkspaceArtifacts,
  orderWorkspaceArtifacts,
  getMultipartPartUrl,
  getArtifactContentUrl,
  rotateArtifactKey,
} from '../workspaces';

describe('api/workspaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listWorkspaces calls GET /artifacts/containers?type=workspace', async () => {
    get.mockResolvedValueOnce([{ id: 'w1' }]);
    const res = await listWorkspaces();
    expect(get).toHaveBeenCalledWith('/artifacts/containers?type=workspace');
    expect(res).toEqual([{ id: 'w1' }]);
  });

  it('createWorkspace calls POST /artifacts with workspace content_type', async () => {
    post.mockResolvedValueOnce({ id: 'w-new', name: 'N' });
    const res = await createWorkspace({ name: 'N', description: 'D' });
    expect(post).toHaveBeenCalledWith('/artifacts', { name: 'N', description: 'D', content_type: 'application/vnd.agience.workspace+json' });
    expect(res.id).toBe('w-new');
  });

  it('listWorkspaceArtifacts normalizes array response to { items }', async () => {
    get.mockResolvedValueOnce([{ id: 'c1' }, { id: 'c2' }]);
    const res = await listWorkspaceArtifacts('w1');
    expect(get).toHaveBeenCalledWith('/artifacts/list?container_id=w1');
    expect(res).toEqual({ items: [{ id: 'c1' }, { id: 'c2' }] });
  });

  it('listWorkspaceArtifacts preserves object response with order_version', async () => {
    get.mockResolvedValueOnce({ items: [{ id: 'c1' }], order_version: 3 });
    const res = await listWorkspaceArtifacts('w2');
    expect(get).toHaveBeenCalledWith('/artifacts/list?container_id=w2');
    expect(res).toEqual({ items: [{ id: 'c1' }], order_version: 3 });
  });

  it('orderWorkspaceArtifacts calls PATCH /artifacts/:id/order', async () => {
    patch.mockResolvedValueOnce({ order_version: 5 });
    const res = await orderWorkspaceArtifacts('w1', ['a', 'b'], 4);
    expect(patch).toHaveBeenCalledWith('/artifacts/w1/order', { ordered_ids: ['a', 'b'], order_version: 4 });
    expect(res).toEqual({ ok: true, version: 5 });
  });

  it('getMultipartPartUrl calls GET /artifacts/:uploadId/multipart-part-url', async () => {
    get.mockResolvedValueOnce({ url: 'https://u', part_number: 1 });
    const res = await getMultipartPartUrl('w1', 'u1', 1);
    expect(get).toHaveBeenCalledWith('/artifacts/u1/multipart-part-url?part_number=1');
    expect(res.url).toBe('https://u');
  });

  it('getArtifactContentUrl calls GET /artifacts/:id/content-url', async () => {
    get.mockResolvedValueOnce({ url: 'https://cdn', expires_in: 300 });
    const res = await getArtifactContentUrl('w1', 'c1');
    expect(get).toHaveBeenCalledWith('/artifacts/c1/content-url');
    expect(res.expires_in).toBe(300);
  });

  it('rotateArtifactKey posts to the key endpoint with key_context', async () => {
    post.mockResolvedValueOnce({
      workspace_id: 'w1',
      artifact_id: 'a1',
      key_id: 'k1',
      key: 'a1:agc_x',
    });

    const res = await rotateArtifactKey('w1', 'a1', 'stream');

    expect(post).toHaveBeenCalledWith('/artifacts/a1/key?key_context=stream', {});
    expect(res.key).toBe('a1:agc_x');
  });
});
