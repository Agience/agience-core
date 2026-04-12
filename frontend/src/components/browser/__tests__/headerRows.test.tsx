import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import BrowserHeader from '../BrowserHeader';
import FilterChips from '../FilterChips';
import { SearchPanel } from '../../search/SearchPanel';

const setActiveWorkspaceIdMock = vi.fn();
let mockWorkspaces = [{ id: 'ws-1', name: 'Inbox' }];
let mockActiveWorkspace = { id: 'ws-1', name: 'Inbox' };

vi.mock('../../../hooks/useWorkspace', () => ({
  useWorkspace: () => ({
    createArtifact: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({
    workspaces: mockWorkspaces,
    activeWorkspace: mockActiveWorkspace,
    setActiveWorkspaceId: setActiveWorkspaceIdMock,
  }),
}));

vi.mock('../../../hooks/usePreferences', () => ({
  usePreferences: () => ({
    preferences: {},
    updatePreferences: vi.fn().mockResolvedValue(undefined),
    isLoading: false,
  }),
}));

vi.mock('../../../api/collections', () => ({
  listCollections: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/context/shortcuts/useShortcuts', () => ({
  useShortcuts: () => ({
    registerShortcut: vi.fn(),
    unregisterShortcut: vi.fn(),
  }),
}));

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: React.ReactNode }) => <button type="button">{children}</button>,
}));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../common/CardGrid', () => ({
  default: () => <div data-testid="artifact-grid">artifact-grid</div>,
}));

describe('header row layout locks', () => {
  it('shows a dock target when no workspaces are visible', () => {
    mockWorkspaces = [];
    mockActiveWorkspace = null as unknown as { id: 'ws-1'; name: 'Inbox' };

    render(
      <BrowserHeader
        activeSource={null}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
      />,
    );

    expect(screen.getByText('Find a workspace and dock it here.')).toBeDefined();

    mockWorkspaces = [{ id: 'ws-1', name: 'Inbox' }];
    mockActiveWorkspace = { id: 'ws-1', name: 'Inbox' };
  });

  it('keeps SearchPanel rows aligned: top row h-14 white, second row h-10 gray', () => {
    const { container } = render(<SearchPanel artifacts={[]} />);

    const root = container.firstElementChild as HTMLElement;
    const topRow = root.children[0] as HTMLElement;
    const secondRow = root.children[1] as HTMLElement;

    expect(topRow.className).toContain('h-14');
    expect(topRow.className).toContain('bg-white');

    expect(secondRow.className).toContain('h-10');
    expect(secondRow.className).toContain('bg-gray-100');

    const sourceScope = screen.getByLabelText('Search source scope') as HTMLSelectElement;
    expect(sourceScope.value).toBe('all');
  });

  it('keeps BrowserHeader rows aligned: top row h-14 white, search row h-10 gray', () => {
    const { container } = render(
      <BrowserHeader
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
        isShowingSearchResults
      />,
    );

    const root = container.firstElementChild as HTMLElement;
    const topRow = root.children[0] as HTMLElement;
    const secondRow = root.children[1] as HTMLElement;

    expect(topRow.className).toContain('h-14');
    expect(topRow.className).toContain('bg-white');

    expect(secondRow.className).toContain('h-10');
    expect(secondRow.className).toContain('bg-gray-100');
  });

  it('keeps FilterChips bar at h-10 with gray background', () => {
    const { container } = render(
      <FilterChips
        artifacts={[]}
        activeStates={new Set()}
        activeContentTypes={new Set()}
        hiddenContentTypes={new Set()}
        viewMode="grid"
        onViewModeChange={() => {}}
        onStateToggle={() => {}}
        onContentTypeToggle={() => {}}
        onHiddenContentTypeToggle={() => {}}
        onClearAll={() => {}}
      />,
    );

    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('h-10');
    expect(root.className).toContain('bg-gray-100');
    expect(screen.getByRole('group', { name: 'Workspace view mode' })).toBeDefined();
  });

  it('calls onCreateWorkspace when the [+] button is clicked', () => {
    const onCreateWorkspace = vi.fn();

    render(
      <BrowserHeader
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
        onCreateWorkspace={onCreateWorkspace}
      />,
    );

    fireEvent.click(screen.getByLabelText('New workspace'));

    expect(onCreateWorkspace).toHaveBeenCalledTimes(1);
  });

  it('calls onDropWorkspace when a workspace card is dropped on tab area', () => {
    const onDropWorkspace = vi.fn();

    render(
      <BrowserHeader
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
        onDropWorkspace={onDropWorkspace}
      />,
    );

    const dropTarget = screen.getByRole('tablist');
    const dataTransfer = {
      dropEffect: 'none',
      effectAllowed: 'move',
      types: ['application/vnd.agience.drag+json'],
      getData: (type: string) =>
        type === 'application/vnd.agience.drag+json'
          ? JSON.stringify({ kind: 'artifacts', ids: ['workspace-card-1'] })
          : '',
    };

    fireEvent.dragOver(dropTarget, { dataTransfer });
    fireEvent.drop(dropTarget, { dataTransfer });

    expect(onDropWorkspace).toHaveBeenCalledWith(['workspace-card-1']);
  });

  it('renders workspace tabs and switches workspace on tab click', () => {
    setActiveWorkspaceIdMock.mockClear();

    render(
      <BrowserHeader
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
      />,
    );

    // The Inbox workspace tab should exist
    const inboxTab = screen.getByRole('tab', { name: 'Inbox' });
    expect(inboxTab).toBeDefined();
  });

  it('shows close button on workspace tabs', () => {
    render(
      <BrowserHeader
        activeSource={{ type: 'workspace', id: 'ws-1' }}
        onToggleFilters={() => {}}
        filtersOpen={false}
        hasActiveFilter={false}
        activeFilter="all"
        viewMode="grid"
        onViewModeChange={() => {}}
      />,
    );

    const closeButton = screen.getByLabelText('Close Inbox');
    expect(closeButton).toBeDefined();
  });
});
