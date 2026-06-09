import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeAll } from 'vitest';

import SidebarEnhanced from '../SidebarEnhanced';

const listWorkspaceMCPServersMock = vi.fn();

vi.mock('../../../hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({
    workspaces: [{ id: 'ws-1', name: 'Workspace One', created_by: 'user-1', order_key: 'A' }],
    activeWorkspace: { id: 'ws-1', name: 'Workspace One', created_by: 'user-1', order_key: 'A' },
    setActiveWorkspaceId: vi.fn(),
    createWorkspace: vi.fn(),
    updateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  }),
}));

vi.mock('../../../context/workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    removeArtifact: vi.fn(),
    artifacts: [],
    importArtifactsByRootIds: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'user-1' } }),
}));

vi.mock('../../../hooks/usePreferences', () => ({
  usePreferences: () => ({
    preferences: {
      sidebarSections: {
        expanded: ['workspaces', 'resources', 'tools'],
        resourcesViewMode: 'by-collection',
        hiddenWorkspaces: [],
        hiddenMcpServers: [],
      },
    },
    updatePreferences: vi.fn(),
  }),
}));

vi.mock('../../../api/mcp', () => ({
  listWorkspaceMCPServers: (...args: unknown[]) => listWorkspaceMCPServersMock(...args),
}));

vi.mock('../../../api/collections', () => ({
  getCollectionArtifacts: vi.fn().mockResolvedValue([]),
}));

vi.mock('../../browser/AdvancedSearch', () => ({
  default: () => <div data-testid="advanced-search" />,
}));

vi.mock('../../common/CardGrid', () => ({
  default: ({ artifacts }: { artifacts: unknown[] }) => <div data-testid="artifact-grid">{artifacts.length}</div>,
}));

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
    unobserve() {}
  }

  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
});

describe('SidebarEnhanced', () => {
  it('renders MCP server-backed resources and tools without relying on a removed config list', async () => {
    listWorkspaceMCPServersMock.mockResolvedValue([
      {
        server: 'agience-core',
        status: 'ok',
        icon: 'agience',
        tools: [{ name: 'search', description: 'Search artifacts' }],
        resources: [
          {
            id: 'collection:c1',
            kind: 'collection',
            title: 'Team Docs',
            mimeType: 'application/vnd.agience.collection+json',
          },
        ],
      },
    ]);

    render(
      <SidebarEnhanced
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onActiveSourceChange={vi.fn()}
        collapsed={false}
      />,
    );

    await waitFor(() => {
      expect(listWorkspaceMCPServersMock).toHaveBeenCalledWith('ws-1');
    });

    expect(await screen.findByText('agience-core')).toBeInTheDocument();
    expect(await screen.findByText('Team Docs')).toBeInTheDocument();
  });
});