import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import FloatingCardWindow from '../FloatingCardWindow';

const viewerSpy = vi.fn(({ state }: { state?: string }) => <div data-testid="generic-viewer">state-{state ?? 'view'}</div>);

vi.mock('@/hooks/useWorkspace', () => ({
  useWorkspace: () => ({
    artifacts: [
      {
        id: 'artifact-1',
        context: JSON.stringify({ title: 'Artifact One', content_type: 'text/plain' }),
        content: 'hello',
        state: 'draft',
        collection_ids: [],
      },
    ],
    displayedArtifacts: [],
    updateArtifact: vi.fn(),
  }),
}));

vi.mock('@/hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({
    activeWorkspaceId: 'ws-1',
    updateWorkspace: vi.fn(),
  }),
}));

vi.mock('@/hooks/useCollections', () => ({
  useCollections: () => ({
    collections: [],
  }),
}));

vi.mock('@/registry/content-types', () => ({
  getContentType: () => ({
    id: 'text',
    defaultMode: 'floating',
    defaultState: 'view',
    states: ['view', 'edit'],
    viewer: async () => ({ default: viewerSpy }),
  }),
}));

vi.mock('@/registry/viewer-map', () => ({
  defaultFactory: async () => ({ default: () => <div data-testid="generic-viewer">generic-viewer</div> }),
}));

vi.mock('@/components/ui/icon-button', () => ({
  IconButton: ({ children, active: _active, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) => (
    <button type="button" {...props}>{children}</button>
  ),
}));

vi.mock('@/components/common/CollectionChip', () => ({
  CollectionChip: () => <div />,
}));

vi.mock('@/components/modals/CollectionPicker', () => ({
  CollectionPicker: () => null,
}));

vi.mock('@/components/containers/ContainerCardViewer', () => ({
  default: () => <div data-testid="container-viewer">container-viewer</div>,
}));

vi.mock('@/hooks/useDebouncedSave', () => ({
  useDebouncedSave: () => ({
    isSaving: false,
    lastSaved: null,
    resetTracking: () => {},
  }),
}));

vi.mock('@/api/collections', () => ({
  addArtifactToCollection: vi.fn(),
}));

describe('FloatingCardWindow', () => {
  it('passes edit state through to the content-type viewer when opened in edit mode', async () => {
    render(
      <FloatingCardWindow
        artifactId="artifact-1"
        zIndex={10}
        initialViewState="edit"
        onClose={() => {}}
      />,
    );

    expect(await screen.findByTestId('generic-viewer')).toHaveTextContent('state-edit');
    expect(viewerSpy).toHaveBeenCalled();
  });
});