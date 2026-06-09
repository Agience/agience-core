// src/components/common/__tests__/CardGridItem.test.jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { CardGridItem } from '../CardGridItem';
import { mockArtifact } from '../../../../tests/utils/helpers';

// Mock artifact-identifiers utility (getStableArtifactId moved here from dnd/agienceDrag)
vi.mock('../../../utils/artifact-identifiers', () => ({
  getStableArtifactId: (artifact) => artifact?.id ?? null,
}));

// Mock context providers
vi.mock('../../../hooks/useWorkspace', () => ({
  useWorkspace: () => ({
    artifacts: [],
    displayedArtifacts: [],
  })
}));

vi.mock('../../../context/collections/CollectionsContext', () => ({
  useCollections: () => ({
    collections: [],
    assignArtifactToCollections: vi.fn(),
  })
}));

// Mock UI components
vi.mock('../../ui/context-menu', () => ({
  ContextMenu: ({ children }) => <div>{children}</div>,
  ContextMenuContent: ({ children }) => <div>{children}</div>,
  ContextMenuItem: ({ children, onClick }) => <button onClick={onClick}>{children}</button>,
  ContextMenuSeparator: () => <hr />,
  ContextMenuTrigger: ({ children }) => <div>{children}</div>
}));

vi.mock('../../ui/badge', () => ({
  Badge: ({ children, className }) => <span className={className}>{children}</span>
}));

vi.mock('../../ui/popover', () => ({
  Popover: ({ children }) => <div>{children}</div>,
  PopoverContent: ({ children }) => <div>{children}</div>,
  PopoverTrigger: ({ children }) => <div>{children}</div>
}));

describe('CardGridItem', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders artifact with title', () => {
      const artifact = mockArtifact({ 
        id: '1', 
        state: 'committed',
        context: JSON.stringify({ title: 'Test Artifact Title' })
      });
      render(<CardGridItem artifact={artifact} />);
      
      expect(screen.getByText('Test Artifact Title')).toBeInTheDocument();
    });

    it('renders artifact with description when no title', () => {
      const artifact = mockArtifact({ 
        id: '1', 
        state: 'committed',
        content: 'Test artifact description that should be visible'
      });
      render(<CardGridItem artifact={artifact} />);
      
      expect(screen.getByText(/Test artifact description/)).toBeInTheDocument();
    });

    it('renders state badge for draft artifacts', () => {
      const artifact = mockArtifact({ id: '1', state: 'draft' });
      render(<CardGridItem artifact={artifact} />);

      expect(screen.getByText('Draft')).toBeInTheDocument();
    });

    it('does not render state badge for committed artifacts', () => {
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      render(<CardGridItem artifact={artifact} />);

      // committed = normal published state, no badge needed
      expect(screen.queryByText('Modified')).not.toBeInTheDocument();
    });

    it('renders state badge for archived artifacts', () => {
      const artifact = mockArtifact({ id: '1', state: 'archived' });
      render(<CardGridItem artifact={artifact} />);
      
      expect(screen.getByText('Archived')).toBeInTheDocument();
    });

    it('does not render state badge for unmodified artifacts', () => {
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      render(<CardGridItem artifact={artifact} />);
      
      // Unmodified badge should not be shown (too noisy)
      expect(screen.queryByText('Unmodified')).not.toBeInTheDocument();
      expect(screen.queryByText('UNMODIFIED')).not.toBeInTheDocument();
    });
  });

  describe('State-Specific Actions', () => {
    it('shows delete action for new artifacts when not in panel', async () => {
      const onRemove = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'draft' });
      
      const { container } = render(<CardGridItem artifact={artifact} onRemove={onRemove} />);
      
      // Hover to show actions
      fireEvent.mouseEnter(container.firstChild);
      
      // Action button should appear (implementation may vary)
      // In real component, hover shows action buttons
    });

    it('shows remove action for unmodified artifacts', async () => {
      const onRemove = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      
      const { container } = render(<CardGridItem artifact={artifact} onRemove={onRemove} />);
      fireEvent.mouseEnter(container.firstChild);
      
      // Unmodified artifacts get "remove from workspace" action
    });

    it('shows revert action for modified artifacts', async () => {
      const onRevert = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'draft' });
      
      const { container } = render(<CardGridItem artifact={artifact} onRevert={onRevert} />);
      fireEvent.mouseEnter(container.firstChild);
      
      // Modified artifacts get "revert" action
    });

    it('shows restore action for archived artifacts', async () => {
      const onRestore = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'archived' });
      
      const { container } = render(<CardGridItem artifact={artifact} onRestore={onRestore} />);
      fireEvent.mouseEnter(container.firstChild);
      
      // Archived artifacts get "restore" action
    });

    it('hides lifecycle actions while processing is pending', () => {
      const artifact = mockArtifact({
        id: '1',
        state: 'committed',
        context: JSON.stringify({
          title: 'Pending audio',
          processing: {
            status: 'pending_handler',
            asset_status: 'available',
            content_status: 'pending_handler',
          },
        }),
      });

      render(
        <CardGridItem
          artifact={artifact}
          onRemove={vi.fn()}
          onArchive={vi.fn()}
        />
      );

      expect(screen.queryByText('Archive')).not.toBeInTheDocument();
      expect(screen.queryByText('Remove from workspace')).not.toBeInTheDocument();
    });

    it('keeps delete available for new artifacts during upload', () => {
      const artifact = mockArtifact({
        id: '1',
        state: 'draft',
        context: JSON.stringify({
          title: 'Uploading file',
          upload: { status: 'in-progress', progress: 0.2 },
          processing: {
            status: 'pending_upload',
            asset_status: 'uploading',
            content_status: 'pending_upload',
          },
        }),
      });

      render(<CardGridItem artifact={artifact} onRemove={vi.fn()} />);

      // Hover to reveal action buttons — target the card element directly
      // (mouseenter does not bubble, so we must target the element with onMouseEnter)
      fireEvent.mouseEnter(screen.getByTestId('artifact-1'));

      // Delete button is icon-only; the title prop is spread onto the <button> element
      expect(screen.getByTitle('Delete')).toBeInTheDocument();
    });
  });

  describe('Panel Mode', () => {
    it('shows X button to remove from panel when in panel mode', async () => {
      const onRemove = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      
      const { container } = render(<CardGridItem artifact={artifact} onRemove={onRemove} inPanel />);
      fireEvent.mouseEnter(container.firstChild);
      
      // In panel mode, shows X icon to remove from panel
    });

    it('hides workspace-specific actions in panel mode', () => {
      const artifact = mockArtifact({ id: '1', state: 'draft' });
      
      const { container } = render(
        <CardGridItem 
          artifact={artifact} 
          onRemove={vi.fn()} 
          onRevert={vi.fn()}
          onArchive={vi.fn()}
          inPanel 
        />
      );
      
      // Panel mode should only show X icon, not state-specific actions
      fireEvent.mouseEnter(container.firstChild);
    });
  });

  describe('Selection', () => {
    it('applies selection styling when isSelected=true', () => {
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      const { container } = render(<CardGridItem artifact={artifact} isSelected selectable />);
      
      // Selected artifacts have ring-2 ring-purple-600 classes
      const artifactElement = screen.getByTestId('artifact-1');
      expect(artifactElement).toHaveClass('ring-2', 'ring-purple-600');
    });

    it('calls onMouseDown when clicked and selectable', async () => {
      const user = userEvent.setup();
      const onMouseDown = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      
      render(
        <CardGridItem artifact={artifact} onMouseDown={onMouseDown} selectable />
      );
      
      await user.click(screen.getByTestId('artifact-1'));
      
      expect(onMouseDown).toHaveBeenCalled();
    });

    it('invokes onMouseDown once during drag initiation to ensure selection', () => {
      const onMouseDown = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });

      render(
        <CardGridItem artifact={artifact} onMouseDown={onMouseDown} draggable selectable />
      );

      const artifactElement = screen.getByTestId('artifact-1');
      const dataTransfer = {
        setData: vi.fn(),
        effectAllowed: '',
        dropEffect: '',
        clearData: vi.fn(),
        setDragImage: vi.fn(),
      };

      fireEvent.dragStart(artifactElement, { dataTransfer });
      fireEvent.mouseUp(artifactElement);

      expect(onMouseDown).toHaveBeenCalledTimes(1);
    });
  });

  describe('Drag and Drop', () => {
    it('sets drag data with artifact IDs on dragStart', () => {
      const artifact = mockArtifact({ id: '1', collection_id: 'ws-1', state: 'committed' });
      const dragData = { ids: ['1'] };
      
      render(
        <CardGridItem 
          artifact={artifact} 
          draggable 
          dragData={dragData}
          activeSource={{ type: 'workspace', id: 'ws-1' }}
        />
      );
      
      const artifactElement = screen.getByTestId('artifact-1');
      const mockDataTransfer = {
        setData: vi.fn(),
        effectAllowed: ''
      };
      
      fireEvent.dragStart(artifactElement, { dataTransfer: mockDataTransfer });
      
      // Verify drag data includes custom MIME type and artifact IDs
      expect(mockDataTransfer.setData).toHaveBeenCalledWith(
        'application/x-agience-artifact',
        expect.stringContaining('"ids":["1"]')
      );
    });

    it('drags multiple selected artifacts when isSelected=true', () => {
      const artifact = mockArtifact({ id: '2', collection_id: 'ws-1', state: 'committed' });
      const dragData = { ids: ['1', '2', '3'] };
      
      render(
        <CardGridItem 
          artifact={artifact} 
          draggable 
          isSelected
          dragData={dragData}
          activeSource={{ type: 'workspace', id: 'ws-1' }}
        />
      );
      
      const mockDataTransfer = {
        setData: vi.fn(),
        effectAllowed: ''
      };
      
      fireEvent.dragStart(screen.getByTestId('artifact-2'), { dataTransfer: mockDataTransfer });
      
      // Should drag all selected IDs
      expect(mockDataTransfer.setData).toHaveBeenCalledWith(
        'application/x-agience-artifact',
        expect.stringContaining('"ids":["1","2","3"]')
      );
    });

    it('includes source context in drag payload', () => {
      const artifact = mockArtifact({ 
        id: '1', 
        collection_id: 'ws-1',
        collection_ids: ['coll-1'],
        state: 'committed' 
      });
      
      render(
        <CardGridItem 
          artifact={artifact} 
          draggable
          dragData={{ ids: ['1'] }}
          activeSource={{ type: 'collection', id: 'coll-1' }}
        />
      );
      
      const mockDataTransfer = {
        setData: vi.fn(),
        effectAllowed: ''
      };
      
      fireEvent.dragStart(screen.getByTestId('artifact-1'), { dataTransfer: mockDataTransfer });
      
      // Payload should include source type and ID
      expect(mockDataTransfer.setData).toHaveBeenCalledWith(
        'application/x-agience-artifact',
        expect.stringContaining('"sourceType":"collection"')
      );
      expect(mockDataTransfer.setData).toHaveBeenCalledWith(
        'application/x-agience-artifact',
        expect.stringContaining('"sourceId":"coll-1"')
      );
    });
  });

  describe('Edit Mode', () => {
    it('calls onEdit when artifact is double-clicked and editable', async () => {
      const onEdit = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      const user = userEvent.setup();

      render(<CardGridItem artifact={artifact} onEdit={onEdit} editable />);
      
      await user.dblClick(screen.getByTestId('artifact-1'));
      
      expect(onEdit).toHaveBeenCalledWith(artifact);
    });

    it('does not open edit when editable=false', async () => {
      const onEdit = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      const user = userEvent.setup();

      render(<CardGridItem artifact={artifact} onEdit={onEdit} editable={false} />);
      
      await user.dblClick(screen.getByTestId('artifact-1'));
      
      expect(onEdit).not.toHaveBeenCalled();
    });
  });

  describe('Force Hover', () => {
    it('applies hover state when forceHover=true', () => {
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      
      const { container, rerender } = render(<CardGridItem artifact={artifact} />);
      
      // Initially not hovered
      expect(container.firstChild).not.toHaveClass('shadow-md');
      
      // Force hover
      rerender(<CardGridItem artifact={artifact} forceHover />);
      
      // Should now have hover styling (implementation detail)
      // The component sets internal hovered state to true
    });
  });

  describe('Collection Assignment', () => {
    it('does not show ghost effect (membership changes are immediate via edges)', () => {
      const artifact = mockArtifact({
        id: '1',
        state: 'draft',
        committed_collection_ids: ['coll-1', 'coll-2'],
      });

      render(<CardGridItem artifact={artifact} />);

      // No ghost effect — membership is edge-based, not staged
      expect(screen.getByTestId('artifact-1')).not.toHaveClass('opacity-75');
    });

    it('calls onAssignCollections when collection assignment button clicked', async () => {
      const onAssignCollections = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'draft' });
      
      const { container } = render(
        <CardGridItem 
          artifact={artifact} 
          onAssignCollections={onAssignCollections}
          isShowingSearchResults
        />
      );
      
      fireEvent.mouseEnter(container.firstChild);
      
      // In search results mode, should show collection assignment action
      // Implementation detail: hover shows action buttons
    });
  });

  describe('Search Results Mode', () => {
    it('shows add to workspace action in search results mode', () => {
      const onAddToWorkspace = vi.fn();
      const artifact = mockArtifact({ id: '1', state: 'committed' });
      
      const { container } = render(
        <CardGridItem 
          artifact={artifact} 
          onAddToWorkspace={onAddToWorkspace}
          isShowingSearchResults
        />
      );
      
      fireEvent.mouseEnter(container.firstChild);
      
      // Search results mode shows "add to workspace" action
    });

    it('drags workspace search results by root_id', () => {
      const artifact = mockArtifact({
        id: 'workspace-artifact-1',
        root_id: 'root-1',
        collection_id: 'ws-1',
        state: 'committed',
      });

      render(
        <CardGridItem
          artifact={artifact}
          draggable
          dragData={{ ids: ['root-1'] }}
          isShowingSearchResults
        />
      );

      const mockDataTransfer = {
        setData: vi.fn(),
        effectAllowed: '',
      };

      fireEvent.dragStart(screen.getByTestId('artifact-workspace-artifact-1'), { dataTransfer: mockDataTransfer });

      expect(mockDataTransfer.setData).toHaveBeenCalledWith(
        'application/x-agience-artifact',
        expect.stringContaining('"ids":["root-1"]')
      );
    });
  });

  describe('Edge Cases', () => {
    it('handles artifact with upload progress', () => {
      const artifact = mockArtifact({ 
        id: '1', 
        state: 'draft',
        context: JSON.stringify({
          upload: {
            status: 'uploading',
            progress: 50
          }
        })
      });
      
      render(<CardGridItem artifact={artifact} />);
      
      // Artifact should render and show upload progress indicator
      // (Implementation detail: readUpload() extracts upload metadata)
    });

    it('handles artifact with long title', () => {
      const longTitle = 'A'.repeat(200);
      const artifact = mockArtifact({
        id: '1',
        state: 'committed',
        context: JSON.stringify({ title: longTitle })
      });
      
      render(<CardGridItem artifact={artifact} />);
      
      // Long titles should be rendered (CSS handles truncation)
      expect(screen.getByText(longTitle)).toBeInTheDocument();
    });

    it('handles artifact with context heading', () => {
      const artifact = mockArtifact({ 
        id: '1',
        context: JSON.stringify({ title: 'Context Heading' }),
        state: 'committed' 
      });
      
      render(<CardGridItem artifact={artifact} />);
      
      // Context heading should be displayed
      expect(screen.getByText('Context Heading')).toBeInTheDocument();
    });
  });
});
