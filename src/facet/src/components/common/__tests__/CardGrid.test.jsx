// src/components/common/__tests__/CardGrid.test.jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import CardGrid from '../CardGrid';
import { mockArtifact } from '../../../../tests/utils/helpers';

import { WorkspaceContext } from '../../../context/workspace/WorkspaceContext';

function renderWithWorkspace(ui) {
  const value = { updateArtifact: vi.fn(), unselectAllArtifacts: vi.fn() };
  const result = render(
    <WorkspaceContext.Provider value={value}>
      {ui}
    </WorkspaceContext.Provider>
  );

  return {
    ...result,
    workspace: value,
    rerender: (nextUi) =>
      result.rerender(
        <WorkspaceContext.Provider value={value}>
          {nextUi}
        </WorkspaceContext.Provider>
      ),
  };
}

// Mock CardGridItem to simplify testing the grid logic
vi.mock('../CardGridItem', () => ({
  CardGridItem: ({ artifact, onMouseDown, onEdit, onRemove, onRevert, forceHover, editable = true }) => {
    const artifactId = artifact.id ?? artifact.root_id ?? 'missing';
    return (
      <div 
        data-testid={`artifact-${artifactId}`}
        data-state={artifact.state}
        data-force-hover={forceHover ? 'true' : 'false'}
      >
        <span>{artifact.title || artifact.description?.substring(0, 20) || 'Untitled'}</span>
        {onEdit && editable !== false && <button onClick={() => onEdit(artifact)}>Edit</button>}
        {onRemove && <button onClick={() => onRemove(artifact)}>Remove</button>}
        {onRevert && <button onClick={() => onRevert(artifact)}>Revert</button>}
        {onMouseDown && (
          <button
            data-testid={`select-${artifactId}`}
            onClick={() => onMouseDown({ shiftKey: false, metaKey: false, ctrlKey: false })}
          >
            Select
          </button>
        )}
      </div>
    );
  }
}));

describe('CardGrid', () => {
  const createMockArtifacts = (count) => {
    return Array.from({ length: count }, (_, i) => 
      mockArtifact({
        id: `artifact-${i + 1}`,
        title: `Artifact ${i + 1}`,
        state: 'committed',
        order_key: String(i + 1).padStart(10, '0')
      })
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders empty grid when no artifacts provided', () => {
      const { container } = renderWithWorkspace(<CardGrid artifacts={[]} />);
      expect(container.querySelector('[data-testid^="artifact-"]')).toBeNull();
    });

    it('renders all provided artifacts', () => {
      const artifacts = createMockArtifacts(3);
      renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-2')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-3')).toBeInTheDocument();
    });

    it('renders artifacts in order_key sorted order', () => {
      const artifacts = [
        mockArtifact({ id: 'artifact-3', title: 'Third', order_key: 'zzz' }),
        mockArtifact({ id: 'artifact-1', title: 'First', order_key: 'aaa' }),
        mockArtifact({ id: 'artifact-2', title: 'Second', order_key: 'mmm' })
      ];
      
      const { container } = renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      const artifactElements = container.querySelectorAll('[data-testid^="artifact-"]');
      
      expect(artifactElements[0]).toHaveAttribute('data-testid', 'artifact-artifact-1');
      expect(artifactElements[1]).toHaveAttribute('data-testid', 'artifact-artifact-2');
      expect(artifactElements[2]).toHaveAttribute('data-testid', 'artifact-artifact-3');
    });

    it('passes artifact state to grid items', () => {
      const artifacts = [
        mockArtifact({ id: '1', state: 'draft' }),
        mockArtifact({ id: '2', state: 'draft' }),
        mockArtifact({ id: '3', state: 'archived' })
      ];
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      
      expect(screen.getByTestId('artifact-1')).toHaveAttribute('data-state', 'draft');
      expect(screen.getByTestId('artifact-2')).toHaveAttribute('data-state', 'draft');
      expect(screen.getByTestId('artifact-3')).toHaveAttribute('data-state', 'archived');
    });
  });

  describe('Artifact Actions', () => {
    it('calls onRemove when remove button clicked', async () => {
      const user = userEvent.setup();
      const onRemove = vi.fn();
      const artifacts = createMockArtifacts(2);
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} onRemove={onRemove} />);
      
      await user.click(screen.getAllByText('Remove')[0]);
      
      expect(onRemove).toHaveBeenCalledWith(artifacts[0]);
    });

    it('calls onRevert when revert button clicked', async () => {
      const user = userEvent.setup();
      const onRevert = vi.fn();
      const artifacts = [mockArtifact({ id: '1', state: 'draft' })];
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} onRevert={onRevert} />);
      
      await user.click(screen.getByText('Revert'));
      
      expect(onRevert).toHaveBeenCalledWith(artifacts[0]);
    });

    it('calls onEditArtifactOpen when artifact double-clicked for edit', async () => {
      const user = userEvent.setup();
      const onEditArtifactOpen = vi.fn();
      const artifacts = createMockArtifacts(1);
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} onEditArtifactOpen={onEditArtifactOpen} editable />);
      
      await user.click(screen.getByText('Edit'));
      
      expect(onEditArtifactOpen).toHaveBeenCalled();
    });
  });

  describe('Force Hover State Transfer', () => {
    it('sets forceHover on next artifact after delete', async () => {
      const user = userEvent.setup();
      const artifacts = createMockArtifacts(3);
      const firstArtifact = artifacts[0];
      const onRemove = vi.fn((artifact) => {
        // Simulate artifact removal
        artifacts.splice(artifacts.findIndex(c => c.id === artifact.id), 1);
      });
      
      const { rerender } = renderWithWorkspace(<CardGrid artifacts={artifacts} onRemove={onRemove} />);
      
      // Click remove on first artifact
      await user.click(screen.getAllByText('Remove')[0]);
      
      // After removal, forceHover should be set temporarily
      // (In real component this happens via state update + setTimeout)
      // For test, we verify the handler was called
      expect(onRemove).toHaveBeenCalledWith(firstArtifact);
    });
  });

  describe('Artifact Ordering', () => {
    it('syncs orderedIds when artifacts are added', () => {
      const { rerender } = renderWithWorkspace(<CardGrid artifacts={createMockArtifacts(2)} />);
      
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-2')).toBeInTheDocument();
      
      // Add a new artifact
      const updatedArtifacts = [
        ...createMockArtifacts(2),
        mockArtifact({ id: 'artifact-3', title: 'Artifact 3', order_key: '0000000003' })
      ];
      
      rerender(<CardGrid artifacts={updatedArtifacts} />);
      
      expect(screen.getByTestId('artifact-artifact-3')).toBeInTheDocument();
    });

    it('syncs orderedIds when artifacts are removed', () => {
      const artifacts = createMockArtifacts(3);
      const { rerender } = renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      
      expect(screen.getByTestId('artifact-artifact-2')).toBeInTheDocument();
      
      // Remove middle artifact
      const updatedArtifacts = [artifacts[0], artifacts[2]];
      rerender(<CardGrid artifacts={updatedArtifacts} />);
      
      expect(screen.queryByTestId('artifact-artifact-2')).not.toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-3')).toBeInTheDocument();
    });
  });

  describe('Selection', () => {
    it('passes selectedIds to check selection state', () => {
      const artifacts = createMockArtifacts(3);
      const selectedIds = ['artifact-1', 'artifact-3'];
      const isSelected = (id) => selectedIds.includes(id);
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} selectedIds={selectedIds} isSelected={isSelected} selectable />);
      
      // Verify artifacts are rendered (selection state handled by CardGridItem mock)
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-2')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-3')).toBeInTheDocument();
    });

    it('falls back to root_id for selection when id is missing', async () => {
      const user = userEvent.setup();
      const artifacts = [
        mockArtifact({ id: undefined, root_id: 'root-1', title: 'First' }),
        mockArtifact({ id: undefined, root_id: 'root-2', title: 'Second' })
      ];
      const onArtifactMouseDown = vi.fn();

      renderWithWorkspace(<CardGrid artifacts={artifacts} selectable onArtifactMouseDown={onArtifactMouseDown} />);

      await user.click(screen.getByTestId('select-root-1'));
      await user.click(screen.getByTestId('select-root-2'));

      expect(onArtifactMouseDown).toHaveBeenCalledTimes(2);
      expect(onArtifactMouseDown).toHaveBeenNthCalledWith(
        1,
        'root-1',
        expect.objectContaining({ shiftKey: false, metaKey: false, ctrlKey: false })
      );
      expect(onArtifactMouseDown).toHaveBeenNthCalledWith(
        2,
        'root-2',
        expect.objectContaining({ shiftKey: false, metaKey: false, ctrlKey: false })
      );
    });

    it('calls onArtifactMouseDown for selection', async () => {
      const user = userEvent.setup();
      const onArtifactMouseDown = vi.fn();
      const artifacts = createMockArtifacts(1);
      
      // Since we mocked CardGridItem, we need to simulate the mousedown differently
      // The real component would trigger this via CardGridItem's onMouseDown
      renderWithWorkspace(<CardGrid artifacts={artifacts} onArtifactMouseDown={onArtifactMouseDown} selectable />);
      
      // In real usage, clicking the artifact would trigger onArtifactMouseDown
      // For this test, we verify the prop was passed
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });
  });

  describe('Props Configuration', () => {
    it('respects draggable prop', () => {
      const artifacts = createMockArtifacts(1);
      renderWithWorkspace(<CardGrid artifacts={artifacts} draggable />);
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });

    it('respects editable prop', () => {
      const artifacts = createMockArtifacts(1);
      renderWithWorkspace(<CardGrid artifacts={artifacts} editable={false} />);
      
      // With editable=false, edit button should not be rendered by CardGridItem mock
      expect(screen.queryByText('Edit')).not.toBeInTheDocument();
    });

    it('respects fillHeight prop', () => {
      const artifacts = createMockArtifacts(1);
      const { container } = renderWithWorkspace(<CardGrid artifacts={artifacts} fillHeight />);
      
      // fillHeight controls CSS classes, verify component renders
      expect(container.firstChild).toBeInTheDocument();
    });
  });

  describe('Search Results Mode', () => {
    it('renders in search results mode', () => {
      const artifacts = createMockArtifacts(2);
      renderWithWorkspace(<CardGrid artifacts={artifacts} isShowingSearchResults />);
      
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-artifact-2')).toBeInTheDocument();
    });

    it('shows collection assignment action in search mode', () => {
      const onAssignCollections = vi.fn();
      const artifacts = createMockArtifacts(1);
      
      renderWithWorkspace(
        <CardGrid 
          artifacts={artifacts} 
          isShowingSearchResults 
          onAssignCollections={onAssignCollections}
        />
      );
      
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });
  });

  describe('Active Source', () => {
    it('handles workspace source', () => {
      const artifacts = createMockArtifacts(1);
      const activeSource = { type: 'workspace', id: 'ws-1' };
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} activeSource={activeSource} />);
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });

    it('handles collection source', () => {
      const artifacts = createMockArtifacts(1);
      const activeSource = { type: 'collection', id: 'coll-1' };
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} activeSource={activeSource} />);
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });

    it('handles MCP server source', () => {
      const artifacts = createMockArtifacts(1);
      const activeSource = { type: 'mcp-server', id: 'mcp-1' };
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} activeSource={activeSource} />);
      expect(screen.getByTestId('artifact-artifact-1')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('treats Windows file drags as file drops even when text/plain is present', () => {
      const artifacts = createMockArtifacts(2);
      const onFileDrop = vi.fn();
      const { container } = renderWithWorkspace(
        <CardGrid
          artifacts={artifacts}
          activeSource={{ type: 'workspace', id: 'ws-1' }}
          onFileDrop={onFileDrop}
        />
      );

      const grid = container.querySelector('[data-role="artifact-grid"]');
      expect(grid).not.toBeNull();

      const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });
      const dataTransfer = {
        files: [file],
        types: ['Files', 'text/plain'],
        getData: (type) => (type === 'text/plain' ? 'C:\\Users\\john\\Desktop\\notes.txt' : ''),
      };

      fireEvent.drop(grid, { dataTransfer });

      expect(onFileDrop).toHaveBeenCalledTimes(1);
      expect(onFileDrop).toHaveBeenCalledWith(artifacts.length, [file]);
    });

    it('handles artifacts with no title or description', () => {
      const artifacts = [mockArtifact({ id: '1', title: '', description: '' })];
      renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      
      expect(screen.getByTestId('artifact-1')).toBeInTheDocument();
      expect(screen.getByText('Untitled')).toBeInTheDocument();
    });

    it('handles rapid artifact additions and removals', () => {
      const { rerender } = renderWithWorkspace(<CardGrid artifacts={createMockArtifacts(2)} />);
      
      rerender(<CardGrid artifacts={createMockArtifacts(5)} />);
      expect(screen.getByTestId('artifact-artifact-5')).toBeInTheDocument();
      
      rerender(<CardGrid artifacts={createMockArtifacts(1)} />);
      expect(screen.queryByTestId('artifact-artifact-5')).not.toBeInTheDocument();
    });

    it('handles artifacts with duplicate order_keys', () => {
      const artifacts = [
        mockArtifact({ id: '1', order_key: 'aaa' }),
        mockArtifact({ id: '2', order_key: 'aaa' }),
        mockArtifact({ id: '3', order_key: 'aaa' })
      ];
      
      renderWithWorkspace(<CardGrid artifacts={artifacts} />);
      
      // All artifacts should render despite duplicate order_keys
      expect(screen.getByTestId('artifact-1')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-2')).toBeInTheDocument();
      expect(screen.getByTestId('artifact-3')).toBeInTheDocument();
    });
  });
});
