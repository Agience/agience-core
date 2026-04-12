import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from '../api';
import { createAPIKey, deleteAPIKey, getAPIKey, listAPIKeys, updateAPIKey } from '../apiKeys';

const mockGet = api.get as ReturnType<typeof vi.fn>;
const mockPost = api.post as ReturnType<typeof vi.fn>;
const mockDelete = api.delete as ReturnType<typeof vi.fn>;
const mockPatch = api.patch as ReturnType<typeof vi.fn>;

describe('api/apiKeys', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates an API key and returns the one-time secret', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        id: 'key-1',
        user_id: 'user-1',
        name: 'VS Code Copilot',
        scopes: ['tool:application/vnd.agience.workspace+json:invoke'],
        resource_filters: { workspaces: ['ws-1'] },
        created_time: '2025-01-01T00:00:00Z',
        modified_time: '2025-01-01T00:00:00Z',
        is_active: true,
        key: 'raw-secret',
      },
    });

    const result = await createAPIKey({
      name: 'VS Code Copilot',
      scopes: ['tool:application/vnd.agience.workspace+json:invoke'],
      resource_filters: { workspaces: ['ws-1'] },
    });

    expect(mockPost).toHaveBeenCalledWith('/api-keys', {
      name: 'VS Code Copilot',
      scopes: ['tool:application/vnd.agience.workspace+json:invoke'],
      resource_filters: { workspaces: ['ws-1'] },
    });
    expect(result.key).toBe('raw-secret');
    expect(result.id).toBe('key-1');
  });

  it('loads API key metadata without exposing the secret', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        id: 'key-1',
        user_id: 'user-1',
        name: 'VS Code Copilot',
        scopes: ['tool:application/vnd.agience.workspace+json:search'],
        resource_filters: { workspaces: ['ws-1'] },
        created_time: '2025-01-01T00:00:00Z',
        modified_time: '2025-01-01T00:00:00Z',
        is_active: true,
      },
    });

    const result = await getAPIKey('key-1');

    expect(mockGet).toHaveBeenCalledWith('/api-keys/key-1');
    expect(result.name).toBe('VS Code Copilot');
    expect('key' in result).toBe(false);
  });

  it('deletes an API key by id', async () => {
    mockDelete.mockResolvedValueOnce({});

    await deleteAPIKey('key-1');

    expect(mockDelete).toHaveBeenCalledWith('/api-keys/key-1');
  });

  it('lists API keys', async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        {
          id: 'key-1',
          user_id: 'user-1',
          name: 'A',
          scopes: ['resource:*:read'],
          resource_filters: {},
          created_time: '2025-01-01T00:00:00Z',
          is_active: true,
        },
      ],
    });

    const result = await listAPIKeys();
    expect(mockGet).toHaveBeenCalledWith('/api-keys');
    expect(result).toHaveLength(1);
  });

  it('updates API key metadata', async () => {
    mockPatch.mockResolvedValueOnce({
      data: {
        id: 'key-1',
        user_id: 'user-1',
        name: 'Updated',
        scopes: ['resource:*:read'],
        resource_filters: {},
        created_time: '2025-01-01T00:00:00Z',
        is_active: true,
      },
    });

    const result = await updateAPIKey('key-1', { name: 'Updated' });
    expect(mockPatch).toHaveBeenCalledWith('/api-keys/key-1', { name: 'Updated' });
    expect(result.name).toBe('Updated');
  });
});