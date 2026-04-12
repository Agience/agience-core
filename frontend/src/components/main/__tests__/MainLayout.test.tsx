import { type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { SearchResponse } from '../../../api/types/search';
import type { Artifact } from '../../../context/workspace/workspace.types';

let mockActiveWorkspaceId = 'ws-1';

const unselectAllArtifactsMock = vi.fn();
const addExistingArtifactMock = vi.fn();
const createArtifactMock = vi.fn();

// Stable references prevent infinite re-render loops: MainLayout has a
// useEffect that depends on `artifacts`. If the mock returns a new []
// every call, React sees a changed dependency and re-renders forever.
const EMPTY_ARTIFACTS: never[] = [];
const EMPTY_IDS: never[] = [];

vi.mock('../../../hooks/useWorkspace', () => ({
  useWorkspace: () => ({
    artifacts: EMPTY_ARTIFACTS,
    displayedArtifacts: EMPTY_ARTIFACTS,
    selectedArtifactIds: EMPTY_IDS,
    unselectAllArtifacts: unselectAllArtifactsMock,
    addExistingArtifact: addExistingArtifactMock,
    createArtifact: createArtifactMock,
  }),
}));

vi.mock('../../../hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({
    workspaces: [
      { id: 'ws-1', name: 'Workspace One', created_by: 'user-1', order_key: 'A' },
      { id: 'ws-2', name: 'Workspace Two', created_by: 'user-1', order_key: 'B' },
    ],
    activeWorkspace: {
      id: mockActiveWorkspaceId,
      name: mockActiveWorkspaceId === 'ws-1' ? 'Workspace One' : 'Workspace Two',
      created_by: 'user-1',
      order_key: mockActiveWorkspaceId === 'ws-1' ? 'A' : 'B',
    },
    activeWorkspaceId: mockActiveWorkspaceId,
    setActiveWorkspaceId: vi.fn(),
    createWorkspace: vi.fn(),
    updateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
  }),
}));

vi.mock('../../../utils/resolveSearchHits', () => ({
  resolveSearchHitsToArtifacts: async (hits: unknown[]): Promise<Artifact[]> =>
    hits.map((h: unknown) => {
      const hit = h as { version_id?: string; id?: string };
      return {
        id: hit.version_id ?? hit.id ?? 'artifact-id',
        context: JSON.stringify({ title: 'Test Artifact', content_type: 'text/plain' }),
        content: 'Test Artifact',
        state: 'committed',
        collection_ids: [],
      } as Artifact;
    }),
}));

vi.mock('@/registry/content-types', () => ({
  getContentType: (artifact: Artifact) => {
    const context = JSON.parse(String(artifact.context || '{}'));
    if (context.content_type === 'application/vnd.agience.workspace+json') {
      return { id: 'workspace', defaultMode: 'grid', isContainer: false };
    }
    if (context.content_type === 'application/vnd.agience.collection+json') {
      return {
        id: 'collection',
        mime: 'application/vnd.agience.collection+json',
        defaultMode: 'grid',
        isContainer: true,
      };
    }
    return { id: 'text', defaultMode: 'floating', isContainer: false };
  },
}));

vi.mock('../../search/SearchPanel', () => ({
  SearchPanel: ({ onResults }: { onResults?: (results: SearchResponse) => void }) => (
    <div>
      <div data-testid="search-panel">search-panel</div>
      <button
        type="button"
        data-testid="trigger-search"
        onClick={() =>
          onResults?.({
            hits: [
              {
                id: 'doc1',
                score: 1,
                root_id: 'root1',
                version_id: 'artifact1',
                collection_id: 'ws-1',
              },
            ],
            total: 1,
            query_text: 'foo',
            used_hybrid: false,
            from: 0,
            size: 1,
          })
        }
      >
        run-search
      </button>
    </div>
  ),
}));

vi.mock('../../workspace/WorkspacePanel', () => ({
  WorkspacePanel: () => <div data-testid="workspace-panel">workspace-panel</div>,
}));

vi.mock('../../layout/TwoPanelLayout', () => ({
  TwoPanelLayout: ({ leftPanel, rightPanel }: { leftPanel: ReactNode; rightPanel: ReactNode }) => (
    <div>
      <div>{leftPanel}</div>
      <div>{rightPanel}</div>
    </div>
  ),
}));

vi.mock('../../command-palette/CommandPalette', () => ({
  default: () => null,
}));

vi.mock('../MainHeader', () => ({
  default: ({ onArtifactCreated }: { onArtifactCreated?: (artifact: Artifact, options?: { startInEditMode?: boolean }) => void }) => (
    <div>
      <div data-testid="header">header</div>
      <button
        type="button"
        data-testid="create-artifact"
        onClick={() => onArtifactCreated?.({
          id: 'new-artifact-1',
          context: JSON.stringify({ title: 'New Artifact', content_type: 'text/plain' }),
          content: 'hello',
          state: 'draft',
          collection_ids: [],
        } as Artifact, { startInEditMode: true })}
      >
        create-artifact
      </button>
      <button
        type="button"
        data-testid="open-artifact"
        onClick={() => onArtifactCreated?.({
          id: 'existing-artifact-1',
          context: JSON.stringify({ title: 'Existing Artifact', content_type: 'text/plain' }),
          content: 'hello',
          state: 'committed',
          collection_ids: [],
        } as Artifact)}
      >
        open-artifact
      </button>
      <button
        type="button"
        data-testid="open-workspace-card"
        onClick={() => onArtifactCreated?.({
          id: 'workspace-card-1',
          context: JSON.stringify({ title: 'Workspace Card', content_type: 'application/vnd.agience.workspace+json' }),
          content: '{}',
          state: 'draft',
          collection_ids: [],
        } as Artifact, { startInEditMode: true })}
      >
        open-workspace-card
      </button>
      <button
        type="button"
        data-testid="open-collection-card"
        onClick={() => onArtifactCreated?.({
          id: 'collection-1',
          context: JSON.stringify({ title: 'Collection One', content_type: 'application/vnd.agience.collection+json' }),
          content: '{}',
          state: 'committed',
          collection_ids: [],
        } as Artifact)}
      >
        open-collection-card
      </button>
    </div>
  ),
}));

vi.mock('../../windows/FloatingCardWindow', () => ({
  default: ({ artifactId, initialViewState }: { artifactId: string; initialViewState?: string }) => (
    <div data-testid={`floating-window-${artifactId}`} data-view-state={initialViewState ?? 'view'}>
      floating-window-{artifactId}
    </div>
  ),
}));

vi.mock('../MainFooter', () => ({
  default: () => null,
}));

import MainLayout from '../MainLayout';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockActiveWorkspaceId = 'ws-1';
});

describe('MainLayout', () => {
  it('renders the two-panel layout with search and workspace panels', async () => {
    render(<MainLayout />);
    expect(await screen.findByTestId('search-panel')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-panel')).toBeInTheDocument();
  });

  it('calls unselectAllArtifacts when the active workspace changes', async () => {
    const { rerender } = render(<MainLayout />);
    await screen.findByTestId('workspace-panel');
    unselectAllArtifactsMock.mockClear();

    mockActiveWorkspaceId = 'ws-2';
    rerender(<MainLayout />);

    await waitFor(() => {
      expect(unselectAllArtifactsMock).toHaveBeenCalled();
    });
  });

  it('resolves search results when SearchPanel fires onResults', async () => {
    render(<MainLayout />);
    await screen.findByTestId('search-panel');

    fireEvent.click(screen.getByTestId('trigger-search'));

    // resolveSearchHitsToArtifacts mock runs; no throw = success
    await waitFor(() => {
      expect(screen.getByTestId('search-panel')).toBeInTheDocument();
    });
  });

  it('opens newly created artifacts in edit mode in the floating viewer', async () => {
    render(<MainLayout />);
    await screen.findByTestId('header');

    fireEvent.click(screen.getByTestId('create-artifact'));

    await waitFor(() => {
      expect(screen.getByTestId('floating-window-new-artifact-1')).toHaveAttribute('data-view-state', 'edit');
    });
  });

  it('opens regular artifact windows in view mode by default', async () => {
    render(<MainLayout />);
    await screen.findByTestId('header');

    fireEvent.click(screen.getByTestId('open-artifact'));

    await waitFor(() => {
      expect(screen.getByTestId('floating-window-existing-artifact-1')).toHaveAttribute('data-view-state', 'view');
    });
  });

  it('opens workspace cards in floating edit mode when edit intent is requested', async () => {
    render(<MainLayout />);
    await screen.findByTestId('header');

    fireEvent.click(screen.getByTestId('open-workspace-card'));

    await waitFor(() => {
      expect(screen.getByTestId('floating-window-workspace-card-1')).toHaveAttribute('data-view-state', 'edit');
    });
  });

  it('opens collection cards in the generic floating card window', async () => {
    render(<MainLayout />);
    await screen.findByTestId('header');

    fireEvent.click(screen.getByTestId('open-collection-card'));

    await waitFor(() => {
      expect(screen.getByTestId('floating-window-collection-1')).toBeInTheDocument();
    });
  });
});
