import { describe, it, expect, vi } from 'vitest';

import { agentHandler } from '../agent';
import type { PaletteState } from '../../palette.types';

vi.mock('../../../../api/agent', () => ({
  extractInformation: vi.fn().mockResolvedValue({
    workspace_id: 'ws-1',
    source_artifact_id: 'c1',
    created_artifact_ids: ['n1', 'n2'],
    unit_count: 2,
  }),
}));

vi.mock('../../../../api/api', () => ({
  post: vi.fn().mockResolvedValue({ ok: true }),
}));

describe('palette agentHandler', () => {
  const baseState: PaletteState = {
    panelData: {
      input: { artifacts: [], text: '' },
      resources: { artifacts: [], resources: [] },
      context: { artifacts: [] },
      prompts: { artifacts: [] },
      instructions: { artifacts: [], text: '' },
      tools: { tools: ['extract_information'] },
      knowledge: { artifacts: [] },
      options: { config: {} },
      agent: { config: {} },
      targets: { collections: [] },
      output: { artifacts: [] },
    },
    panelStatus: {} as PaletteState['panelStatus'],
    updatePanelStatus: (() => {}) as PaletteState['updatePanelStatus'],
  };

  it('infers source + artifacts from selection and writes a summary output artifact', async () => {
    const next = await agentHandler(baseState, {
      userId: 'user-1',
      workspaceId: 'ws-1',
      selectedArtifactIds: ['c1', 'c2', 'c3'],
    });

    expect(next.panelData.output.artifacts).toHaveLength(1);
    expect(next.panelData.output.artifacts[0].content).toContain('extract_information');
    expect(next.panelData.output.artifacts[0].content).toContain('source_artifact_id: c1');
    expect(next.panelData.output.artifacts[0].content).toContain('context_artifact_ids: c2, c3');
  });

  it('emits an error output artifact when no workspace is active', async () => {
    const next = await agentHandler(baseState, {
      userId: 'user-1',
      workspaceId: '',
      selectedArtifactIds: ['c1'],
    });

    expect(next.panelData.output.artifacts).toHaveLength(1);
    expect(next.panelData.output.artifacts[0].content).toContain('No active workspace');
  });
});
