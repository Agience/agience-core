// src/api/__tests__/mcp.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from '../api';
import {
  listWorkspaceMCPServers,
  importMCPResources,
  readMCPResource,
} from '../mcp';

const mockGet = api.get as ReturnType<typeof vi.fn>;
const mockPost = api.post as ReturnType<typeof vi.fn>;

describe('api/mcp — listWorkspaceMCPServers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls GET /mcp/workspaces/:id/servers and returns server list', async () => {
    const servers = [
      {
        server: 'agience-core',
        tools: [{ name: 'search', description: 'Search artifacts' }],
        resources: [],
        status: 'ok',
      },
      {
        server: 'artifact-abc',
        tools: [{ name: 'list_items' }],
        resources: [{ id: 'r1', kind: 'item', uri: 'agience://r1', title: 'Resource 1' }],
        status: 'ok',
      },
    ];
    mockGet.mockResolvedValueOnce({ data: servers });

    const result = await listWorkspaceMCPServers('ws-123');

    expect(mockGet).toHaveBeenCalledWith('/mcp/workspaces/ws-123/servers');
    expect(result).toHaveLength(2);
    expect(result[0].server).toBe('agience-core');
    expect(result[1].tools[0].name).toBe('list_items');
  });

  it('returns empty list for workspace with no configured servers', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });

    const result = await listWorkspaceMCPServers('ws-empty');

    expect(result).toEqual([]);
  });

  it('propagates API errors', async () => {
    mockGet.mockRejectedValueOnce(new Error('Unauthorized'));

    await expect(listWorkspaceMCPServers('ws-1')).rejects.toThrow('Unauthorized');
  });
});

describe('api/mcp — importMCPResources (Phase 7D: artifact-native dispatch)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts to /artifacts/{server_id}/op/resources_import and returns canonical shape', async () => {
    mockPost.mockResolvedValueOnce({ data: { created_artifact_ids: ['c1', 'c2'], count: 2 } });

    const resources = [
      { id: 'r1', kind: 'item', uri: 'agience://r1', title: 'Res 1' },
      { id: 'r2', kind: 'item', uri: 'agience://r2', title: 'Res 2' },
    ];
    const result = await importMCPResources('ws-123', 'agience-core', resources);

    expect(mockPost).toHaveBeenCalledWith(
      '/artifacts/agience-core/op/resources_import',
      {
        workspace_id: 'ws-123',
        resources,
      }
    );
    expect(result.count).toBe(2);
    expect(result.artifact_ids).toEqual(['c1', 'c2']);
  });

  it('handles empty resource list (count: 0)', async () => {
    mockPost.mockResolvedValueOnce({ data: { created_artifact_ids: [], count: 0 } });

    const result = await importMCPResources('ws-123', 'agience-core', []);

    expect(result.count).toBe(0);
    expect(result.artifact_ids).toEqual([]);
  });

  it('works with a server artifact UUID', async () => {
    mockPost.mockResolvedValueOnce({ data: { created_artifact_ids: ['c3'], count: 1 } });

    const resources = [{ id: 'r3', kind: 'document', uri: 'file://doc.txt', title: 'Doc' }];
    await importMCPResources('ws-1', 'artifact-mcp-server-id', resources);

    const url = mockPost.mock.calls[0][0];
    expect(url).toBe('/artifacts/artifact-mcp-server-id/op/resources_import');
  });

  it('propagates import errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Server unreachable'));

    await expect(
      importMCPResources('ws-1', 'agience-core', [])
    ).rejects.toThrow('Server unreachable');
  });
});

describe('api/mcp — readMCPResource (Phase 7D: artifact-native dispatch)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts to /artifacts/{server_id}/op/resources_read with {uri, workspace_id}', async () => {
    const contents = {
      uri: 'agience://collection/c1',
      name: 'My Collection',
      mimeType: 'application/json',
      text: '{"artifacts":[]}',
    };
    mockPost.mockResolvedValueOnce({ data: contents });

    const result = await readMCPResource('agience-core', 'agience://collection/c1', 'ws-1');

    expect(mockPost).toHaveBeenCalledWith(
      '/artifacts/agience-core/op/resources_read',
      {
        uri: 'agience://collection/c1',
        workspace_id: 'ws-1',
      }
    );
    expect(result.uri).toBe('agience://collection/c1');
    expect(result.name).toBe('My Collection');
    expect(result.text).toBe('{"artifacts":[]}');
  });

  it('works with a server artifact UUID', async () => {
    mockPost.mockResolvedValueOnce({
      data: { uri: 'external://doc', name: 'External Doc', mimeType: 'text/plain', text: 'content' },
    });

    await readMCPResource('artifact-server-abc', 'external://doc', 'ws-1');

    const url = mockPost.mock.calls[0][0];
    expect(url).toBe('/artifacts/artifact-server-abc/op/resources_read');
    const body = mockPost.mock.calls[0][1];
    expect(body.uri).toBe('external://doc');
  });

  it('propagates read errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Resource not found'));

    await expect(
      readMCPResource('agience-core', 'agience://missing')
    ).rejects.toThrow('Resource not found');
  });
});


