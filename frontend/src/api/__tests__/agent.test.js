// src/api/__tests__/agent.test.js
// Tests for api/agent.ts (loadDemoData, extractUnits/extractInformation)
// NOTE: invokeAgent was removed in favour of the unified /agents/invoke pattern;
//       only the typed helper functions (loadDemoData, extractInformation) are
//       tested here.
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  post: vi.fn(),
}));

import { post } from '../api';
import { loadDemoData, extractUnits, extractInformation } from '../agent';

describe('api/agent', () => {
  beforeEach(() => {
    // resetAllMocks clears both call history AND pending mockResolvedValueOnce
    // queues, preventing stale values leaking between tests.
    vi.resetAllMocks();
  });

  describe('loadDemoData', () => {
    it('calls /agents/invoke with the demo_data agent and all params', async () => {
      const mockResponse = {
        workspaces_created: 2,
        workspace_ids: ['ws-1', 'ws-2'],
        workspace_artifacts_created: 10,
        agience_guide_added: true,
        message: 'Demo data loaded successfully',
      };

      post.mockResolvedValueOnce(mockResponse);

      const request = {
        topics: ['Technology', 'Science', 'Art'],
        num_workspaces: 2,
        artifacts_per_workspace: 8,
        include_agience_guide: true,
      };

      const result = await loadDemoData(request);

      expect(post).toHaveBeenCalledWith('/agents/invoke', {
        operator: 'demo_data',
        operator_params: {
          topics: ['Technology', 'Science', 'Art'],
          num_workspaces: 2,
          artifacts_per_workspace: 8,
          include_agience_guide: true,
        },
      });

      expect(result).toEqual(mockResponse);
    });

    it('handles a minimal (empty) request — all operator_params are undefined', async () => {
      const mockResponse = {
        workspaces_created: 0,
        workspace_ids: [],
        workspace_artifacts_created: 0,
        agience_guide_added: false,
        message: 'No data generated',
      };

      post.mockResolvedValueOnce(mockResponse);

      const result = await loadDemoData({});

      expect(post).toHaveBeenCalledWith('/agents/invoke', {
        operator: 'demo_data',
        operator_params: {
          topics: undefined,
          num_workspaces: undefined,
          artifacts_per_workspace: undefined,
          include_agience_guide: undefined,
        },
      });

      expect(result).toEqual(mockResponse);
    });

    it('includes agience_guide_added flag in the response when requested', async () => {
      const mockResponse = {
        workspaces_created: 0,
        workspace_ids: [],
        workspace_artifacts_created: 0,
        agience_guide_added: true,
        message: 'Agience guide added',
      };

      post.mockResolvedValueOnce(mockResponse);

      const result = await loadDemoData({ include_agience_guide: true });

      expect(post).toHaveBeenCalledWith(
        '/agents/invoke',
        expect.objectContaining({
          operator: 'demo_data',
          operator_params: expect.objectContaining({ include_agience_guide: true }),
        })
      );

      expect(result.agience_guide_added).toBe(true);
    });

    it('propagates backend errors', async () => {
      post.mockRejectedValueOnce(new Error('Demo data generation failed'));

      await expect(loadDemoData({ num_workspaces: 5 }))
        .rejects.toThrow('Demo data generation failed');
    });
  });

  describe('extractUnits', () => {
    it('posts the extract_units operator with workspace and source artifact ids', async () => {
      post.mockResolvedValueOnce({
        workspace_id: 'ws-1',
        source_artifact_id: 'art-1',
        created_artifact_ids: ['art-2', 'art-3'],
        unit_count: 2,
      });

      const result = await extractUnits('ws-1', 'art-1');

      expect(post).toHaveBeenCalledWith('/agents/invoke', {
        operator: 'extract_units:extract_units',
        workspace_id: 'ws-1',
        params: {
          source_artifact_id: 'art-1',
          artifact_artifact_ids: [],
        },
      });
      expect(result.created_artifact_ids).toEqual(['art-2', 'art-3']);
      expect(result.unit_count).toBe(2);
    });

    it('passes through optional artifact_artifact_ids when provided', async () => {
      post.mockResolvedValueOnce({
        workspace_id: 'ws-1',
        source_artifact_id: 'art-1',
        created_artifact_ids: ['art-4'],
      });

      await extractUnits('ws-1', 'art-1', ['ctx-a', 'ctx-b']);

      const [, payload] = post.mock.calls[0];
      expect(payload.params.artifact_artifact_ids).toEqual(['ctx-a', 'ctx-b']);
    });

    it('propagates backend errors', async () => {
      post.mockRejectedValueOnce(new Error('extraction failed'));
      await expect(extractUnits('ws-1', 'art-1')).rejects.toThrow('extraction failed');
    });
  });

  describe('extractInformation (alias for extractUnits)', () => {
    it('is the same function reference as extractUnits', () => {
      expect(extractInformation).toBe(extractUnits);
    });

    it('forwards all arguments identically to extractUnits', async () => {
      post.mockResolvedValueOnce({
        workspace_id: 'ws-2',
        source_artifact_id: 'art-9',
        created_artifact_ids: ['art-10'],
      });

      await extractInformation('ws-2', 'art-9', ['extra-ctx']);

      const [, payload] = post.mock.calls[0];
      expect(payload.operator).toBe('extract_units:extract_units');
      expect(payload.workspace_id).toBe('ws-2');
      expect(payload.params.source_artifact_id).toBe('art-9');
      expect(payload.params.artifact_artifact_ids).toEqual(['extra-ctx']);
    });
  });
});
