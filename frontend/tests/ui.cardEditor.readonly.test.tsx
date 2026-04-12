import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

// Mocks for hooks used by CardEditor
vi.mock('../src/hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({ activeWorkspaceId: 'ws-1' }),
}));

vi.mock('../src/hooks/useWorkspace', () => {
  return {
    useWorkspace: () => ({
      artifacts: [], // empty: ensures the artifact is treated as a collection artifact (read-only)
      displayedArtifacts: [
        {
          id: 'c1',
          state: 'committed',
          context: JSON.stringify({ title: 'Guide Intro', description: 'Welcome', tags: ['guide'] }),
          content: 'Hello World',
          committed_collection_ids: ['col1'],
          created_time: '2024-01-01T00:00:00Z',
          modified_time: '2024-01-01T00:00:00Z',
        },
      ],
      removeArtifact: vi.fn(),
      revertArtifact: vi.fn(),
      updateArtifact: vi.fn(),
    }),
  };
});

vi.mock('../src/hooks/useCollections', () => {
  return {
    useCollections: () => ({
      collections: [{ id: 'col1', name: 'Agience Guide' }],
    }),
  };
});

vi.mock('../src/context/shortcuts/useShortcuts', () => {
  return {
    useShortcuts: () => ({ registerShortcut: () => () => {} }),
  };
});

vi.mock('../src/hooks/useDebouncedSave', () => {
  return {
    useDebouncedSave: () => ({ isSaving: false, lastSaved: null, forceSave: vi.fn() }),
  };
});

vi.mock('../src/context/danger-confirm/useDialog', () => {
  return {
    useDialog: () => ({ confirm: async () => true }),
  };
});

// Import after mocks so the component uses mocked hooks
import { CardEditor } from '../src/components/preview/CardEditor';
import { DialogProvider } from '../src/context/dialog/DialogProvider';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <DialogProvider>
      {ui}
    </DialogProvider>
  );
}

describe('CardEditor - read-only behavior for collection artifacts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides Edit and Change controls and renders committed chip', () => {
    renderWithProviders(<CardEditor artifactId="c1" />);

    // No edit button for collection artifacts
    expect(screen.queryByText('Edit')).toBeNull();

    // No Change button for collection membership (read-only)
    expect(screen.queryByText('Change')).toBeNull();

    // The collection chip should be rendered as committed (solid)
    // CollectionChip adds a title attribute when status = committed
    const committedChip = screen.getByTitle('Committed to Agience Guide');
    expect(committedChip).toBeTruthy();
  });

  it('does not enter content edit mode on click for collection artifacts', () => {
    renderWithProviders(<CardEditor artifactId="c1" />);

    // Click on content area; for collection artifacts, this should do nothing
    // We target by the content text since ContentRenderer renders the text content
    const contentNode = screen.getByText('Hello World');
    fireEvent.click(contentNode);

    // There should be no markdown editor or textarea appearing as a result of the click
    expect(screen.queryByRole('textbox')).toBeNull();
  });
});
