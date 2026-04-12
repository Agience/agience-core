// src/api/__tests__/artifacts.test.ts
// Tests for api/artifacts.ts — unified artifact and grant API
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../api';
import {
  createArtifact,
  getArtifact,
  updateArtifact,
  deleteArtifact,
  addItemToContainer,
  invokeArtifact,
  searchArtifacts,
  createGrant,
  getGrant,
  updateGrant,
  deleteGrant,
  claimInvite,
  acceptGrant,
} from '../artifacts';

const mockGet = get as ReturnType<typeof vi.fn>;
const mockPost = post as ReturnType<typeof vi.fn>;
const mockPatch = patch as ReturnType<typeof vi.fn>;
const mockDel = del as ReturnType<typeof vi.fn>;

describe('api/artifacts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // Artifact CRUD
  // ─────────────────────────────────────────────────────────────────────────────

  describe('createArtifact', () => {
    it('POSTs to /artifacts with container_id, context, and content', async () => {
      const artifact = { id: 'art-1', collection_id: 'ws-1', state: 'draft' };
      mockPost.mockResolvedValueOnce(artifact);

      const result = await createArtifact('ws-1', '{"title":"Hello"}', 'body text');

      expect(mockPost).toHaveBeenCalledWith('/artifacts', {
        container_id: 'ws-1',
        context: '{"title":"Hello"}',
        content: 'body text',
      });
      expect(result).toEqual(artifact);
    });

    it('omits content when not provided', async () => {
      mockPost.mockResolvedValueOnce({ id: 'art-2' });

      await createArtifact('ws-1', '{}');

      const [, body] = mockPost.mock.calls[0];
      expect(body.content).toBeUndefined();
    });
  });

  describe('getArtifact', () => {
    it('GETs /artifacts/{id}', async () => {
      const artifact = { id: 'art-1', state: 'committed' };
      mockGet.mockResolvedValueOnce(artifact);

      const result = await getArtifact('art-1');

      expect(mockGet).toHaveBeenCalledWith('/artifacts/art-1');
      expect(result).toEqual(artifact);
    });
  });

  describe('updateArtifact', () => {
    it('PATCHes /artifacts/{id} with the updates payload', async () => {
      const updated = { id: 'art-1', state: 'committed' };
      mockPatch.mockResolvedValueOnce(updated);

      const result = await updateArtifact('art-1', { context: '{"title":"New"}' });

      expect(mockPatch).toHaveBeenCalledWith('/artifacts/art-1', {
        context: '{"title":"New"}',
      });
      expect(result).toEqual(updated);
    });
  });

  describe('deleteArtifact', () => {
    it('DELETEs /artifacts/{id}', async () => {
      mockDel.mockResolvedValueOnce(undefined);

      await deleteArtifact('art-1');

      expect(mockDel).toHaveBeenCalledWith('/artifacts/art-1');
    });
  });

  describe('addItemToContainer', () => {
    it('POSTs to /artifacts — same shape as createArtifact', async () => {
      mockPost.mockResolvedValueOnce({ id: 'art-3' });

      await addItemToContainer('col-1', '{"title":"Imported"}', 'some content');

      expect(mockPost).toHaveBeenCalledWith('/artifacts', {
        container_id: 'col-1',
        context: '{"title":"Imported"}',
        content: 'some content',
      });
    });

    it('omits content when not provided', async () => {
      mockPost.mockResolvedValueOnce({ id: 'art-4' });

      await addItemToContainer('col-1', '{}');

      const [, body] = mockPost.mock.calls[0];
      expect(body.content).toBeUndefined();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // Invoke
  // ─────────────────────────────────────────────────────────────────────────────

  describe('invokeArtifact', () => {
    it('POSTs to /artifacts/{id}/invoke with all fields', async () => {
      const invokeResult = { status: 'completed', output: 'result text' };
      mockPost.mockResolvedValueOnce(invokeResult);

      const result = await invokeArtifact(
        'op-1',
        'run this',
        { strategy: 'fast' },
        'ws-1',
        ['art-a', 'art-b'],
      );

      expect(mockPost).toHaveBeenCalledWith('/artifacts/op-1/invoke', {
        input: 'run this',
        params: { strategy: 'fast' },
        workspace_id: 'ws-1',
        artifacts: ['art-a', 'art-b'],
      });
      expect(result).toEqual(invokeResult);
    });

    it('sends undefined fields when optional args are omitted', async () => {
      mockPost.mockResolvedValueOnce({ status: 'completed' });

      await invokeArtifact('op-2');

      const [, body] = mockPost.mock.calls[0];
      expect(body.input).toBeUndefined();
      expect(body.params).toBeUndefined();
      expect(body.workspace_id).toBeUndefined();
      expect(body.artifacts).toBeUndefined();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // Search
  // ─────────────────────────────────────────────────────────────────────────────

  describe('searchArtifacts', () => {
    it('POSTs to /artifacts/search with query_text', async () => {
      const searchResult = { hits: [], total: 0 };
      mockPost.mockResolvedValueOnce(searchResult);

      const result = await searchArtifacts('machine learning');

      expect(mockPost).toHaveBeenCalledWith('/artifacts/search', {
        query_text: 'machine learning',
        scope: undefined,
        source_types: undefined,
        content_types: undefined,
      });
      expect(result).toEqual(searchResult);
    });

    it('forwards scope and contentTypes options', async () => {
      mockPost.mockResolvedValueOnce({ hits: [], total: 0 });

      await searchArtifacts('science', {
        scope: ['ws-1', 'col-1'],
        contentTypes: ['application/pdf'],
      });

      const [, body] = mockPost.mock.calls[0];
      expect(body.scope).toEqual(['ws-1', 'col-1']);
      expect(body.content_types).toEqual(['application/pdf']);
    });

    it('handles partial options (only scope provided)', async () => {
      mockPost.mockResolvedValueOnce({ hits: [], total: 0 });

      await searchArtifacts('art', { scope: ['ws-2'] });

      const [, body] = mockPost.mock.calls[0];
      expect(body.scope).toEqual(['ws-2']);
      expect(body.source_types).toBeUndefined();
      expect(body.content_types).toBeUndefined();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // Grant management
  // ─────────────────────────────────────────────────────────────────────────────

  describe('createGrant', () => {
    it('POSTs to /grants with resource_id, grantee_type, and permissions', async () => {
      const grant = { id: 'g-1', resource_id: 'col-1' };
      mockPost.mockResolvedValueOnce(grant);

      const result = await createGrant('col-1', 'user', { can_read: true, can_write: false });

      expect(mockPost).toHaveBeenCalledWith('/grants', expect.objectContaining({
        resource_id: 'col-1',
        grantee_type: 'user',
        can_read: true,
        can_write: false,
      }));
      expect(result).toEqual(grant);
    });

    it('includes optional target_entity and max_claims when provided', async () => {
      mockPost.mockResolvedValueOnce({ id: 'g-2' });

      await createGrant('col-1', 'user', { can_read: true }, {
        targetEntity: 'user-99',
        targetEntityType: 'person',
        maxClaims: 5,
      });

      const [, body] = mockPost.mock.calls[0];
      expect(body.target_entity).toBe('user-99');
      expect(body.target_entity_type).toBe('person');
      expect(body.max_claims).toBe(5);
    });

    it('sends undefined optional fields when not provided', async () => {
      mockPost.mockResolvedValueOnce({ id: 'g-3' });

      await createGrant('col-1', 'user', { can_read: true });

      const [, body] = mockPost.mock.calls[0];
      expect(body.target_entity).toBeUndefined();
      expect(body.max_claims).toBeUndefined();
    });
  });

  describe('getGrant', () => {
    it('GETs /grants/{id}', async () => {
      const grant = { id: 'g-1', can_read: true };
      mockGet.mockResolvedValueOnce(grant);

      const result = await getGrant('g-1');

      expect(mockGet).toHaveBeenCalledWith('/grants/g-1');
      expect(result).toEqual(grant);
    });
  });

  describe('updateGrant', () => {
    it('PATCHes /grants/{id} with updates', async () => {
      const updated = { id: 'g-1', can_write: true };
      mockPatch.mockResolvedValueOnce(updated);

      const result = await updateGrant('g-1', { can_write: true });

      expect(mockPatch).toHaveBeenCalledWith('/grants/g-1', { can_write: true });
      expect(result).toEqual(updated);
    });
  });

  describe('deleteGrant', () => {
    it('DELETEs /grants/{id}', async () => {
      mockDel.mockResolvedValueOnce(undefined);

      await deleteGrant('g-1');

      expect(mockDel).toHaveBeenCalledWith('/grants/g-1');
    });
  });

  describe('claimInvite', () => {
    it('POSTs to /grants/claim with the token', async () => {
      const grant = { id: 'g-5', claimed: true };
      mockPost.mockResolvedValueOnce(grant);

      const result = await claimInvite('invite-token-abc');

      expect(mockPost).toHaveBeenCalledWith('/grants/claim', { token: 'invite-token-abc' });
      expect(result).toEqual(grant);
    });
  });

  describe('acceptGrant', () => {
    it('POSTs to /grants/{id}/accept with an empty body', async () => {
      const grant = { id: 'g-6', accepted: true };
      mockPost.mockResolvedValueOnce(grant);

      const result = await acceptGrant('g-6');

      expect(mockPost).toHaveBeenCalledWith('/grants/g-6/accept', {});
      expect(result).toEqual(grant);
    });
  });
});
