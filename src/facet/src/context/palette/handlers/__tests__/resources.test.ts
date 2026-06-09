import { describe, expect, it, vi } from 'vitest';

import { resourcesHandler } from '../resources';
import type { PaletteState } from '../../palette.types';

const readMCPResourceMock = vi.fn();

vi.mock('../../../../api/mcp', () => ({
  readMCPResource: (...args: unknown[]) => readMCPResourceMock(...args),
}));

const baseState: PaletteState = {
  panelData: {
    input: { artifacts: [], text: '' },
    resources: {
      artifacts: [],
      resources: [{ server: 'agience-core', uri: 'agience://collection/c1', title: 'Collection 1' }],
    },
    context: { artifacts: [] },
    prompts: { artifacts: [] },
    instructions: { artifacts: [], text: '' },
    tools: { tools: [] },
    knowledge: { artifacts: [] },
    options: { config: {} },
    agent: { config: {} },
    targets: { collections: [] },
    output: { artifacts: [] },
  },
  panelStatus: {} as PaletteState['panelStatus'],
  updatePanelStatus: (() => {}) as PaletteState['updatePanelStatus'],
};

describe('palette resourcesHandler', () => {
  it('reads MCP resources using the active workspace id and adds them as context artifacts', async () => {
    readMCPResourceMock.mockResolvedValue({
      uri: 'agience://collection/c1',
      name: 'Collection 1',
      mimeType: 'text/markdown',
      text: 'hello world',
    });

    const next = await resourcesHandler(baseState, { workspaceId: 'ws-1' });

    expect(readMCPResourceMock).toHaveBeenCalledWith('agience-core', 'agience://collection/c1', 'ws-1');
    expect(next.panelData.context.artifacts).toHaveLength(1);
    expect(next.panelData.context.artifacts[0].content).toBe('hello world');
    expect(next.panelData.context.artifacts[0].context).toContain('text/markdown');
  });
});