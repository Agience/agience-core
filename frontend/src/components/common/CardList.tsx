// src/components/common/CardList.tsx
import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Artifact } from '../../context/workspace/workspace.types';
import { CardListItem } from './CardListItem';
import { getStableArtifactId } from '@/utils/artifact-identifiers';

const DND_MIME = 'application/x-agience-artifact';

function getArtifactListId(artifact: Artifact, isShowingSearchResults = false): string | null {
  if (isShowingSearchResults && artifact.root_id != null) {
    const root = String(artifact.root_id).trim();
    if (root) return root;
  }
  return getStableArtifactId(artifact);
}

export interface DragData {
  type: 'artifact';
  artifactId: string;
  sourceWorkspaceId?: string;
  sourceCollectionId?: string;
  sourceType?: string;
  sourceId?: string;
  rootIds?: string[];
  versionIds?: string[];
  timestamp: number;
  // Multi-select support
  ids?: string[];
}

interface CardListProps {
  artifacts: Artifact[];
  artifactCountsById?: Record<string, number>;
  /** Source context for drag operations */
  sourceWorkspaceId?: string;
  sourceCollectionId?: string;
  /** Callback for artifact clicks (e.g., single-select or multi-select with Shift/Cmd) */
  onArtifactMouseDown?: (id: string, e: React.MouseEvent | React.DragEvent) => void;
  /** Returns whether an artifact is currently selected */
  isSelected?: (id: string) => boolean;
  /** Called when an artifact is dragged to a new position (index-based) */
  onReorder?: (artifactId: string, targetIndex: number, insertAfter?: boolean) => void;
  /** Called when an artifact is deleted/removed */
  onRemove?: (artifact: Artifact) => void;
  /** Called when an artifact is reverted to previous state */
  onRevert?: (artifact: Artifact) => void;
  /** Called when an artifact is archived */
  onArchive?: (artifact: Artifact) => void;
  /** Called when an artifact is restored from archived state */
  onRestore?: (artifact: Artifact) => void;
  /** File drop handler */
  onFileDrop?: (files: File[], insertAtIndex?: number) => void;
  onArtifactDrop?: (
    targetIndex: number,
    draggedIds: string[],
    dragPayload?: {
      sourceType?: string;
      sourceId?: string;
      workspaceId?: string;
      collectionIds?: string[];
      rootIds?: string[];
      versionIds?: string[];
    },
  ) => void;
  /** Whether artifacts are selectable (show checkboxes) */
  selectable?: boolean;
  /** Whether artifacts are draggable for reordering */
  draggable?: boolean;
  /** Whether artifacts are editable */
  editable?: boolean;
  /** Whether this is a panel view (affects some actions) */
  inPanel?: boolean;
  /** Called after an artifact is deleted to transfer hover state */
  onArtifactDeleted?: (deletedIndex: number) => void;
  /** Called when edit is triggered (to select artifact and show in preview pane) */
  onEditArtifactOpen?: () => void;
  /** Called when an artifact is opened (e.g., floating window) */
  onOpenArtifact?: (artifact: Artifact) => void;
  /** Called when a search result artifact is added to the active workspace. */
  onAddToWorkspace?: (artifact: Artifact) => void;
  /** Called when assigning an artifact to one or more collections. */
  onAssignCollections?: (artifact: Artifact) => void;
  /** Whether the list is showing search results (affects context menu actions). */
  isShowingSearchResults?: boolean;
}

export default function CardList({
  artifacts,
  artifactCountsById = {},
  sourceWorkspaceId,
  sourceCollectionId,
  onArtifactMouseDown,
  isSelected,
  onReorder,
  onRemove,
  onRevert,
  onArchive,
  onRestore,
  onFileDrop,
  onArtifactDrop,
  selectable = false,
  draggable = true,
  editable = true,
  inPanel = false,
  onArtifactDeleted,
  onEditArtifactOpen,
  onOpenArtifact,
  onAddToWorkspace,
  onAssignCollections,
  isShowingSearchResults = false,
}: CardListProps) {
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [dragAfter, setDragAfter] = useState(false);
  const [forceHoverIndex, setForceHoverIndex] = useState<number | null>(null);
  const preventEditRef = useRef(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Clear force hover after 300ms
  useEffect(() => {
    if (forceHoverIndex !== null) {
      const timer = setTimeout(() => setForceHoverIndex(null), 300);
      return () => clearTimeout(timer);
    }
  }, [forceHoverIndex]);

  // Clear prevent edit after 300ms (no dependencies needed - ref mutation doesn't trigger re-render)
  useEffect(() => {
    if (preventEditRef.current) {
      const timer = setTimeout(() => { preventEditRef.current = false; }, 300);
      return () => clearTimeout(timer);
    }
  });

  // Edit handlers
  const handleEdit = useCallback((artifact: Artifact) => {
    if (preventEditRef.current) return;
    // Select the artifact and show in preview pane (inline editor)
    const stableId = getArtifactListId(artifact, isShowingSearchResults);
    if (stableId) {
      onArtifactMouseDown?.(stableId, {} as React.MouseEvent);
    }
    onEditArtifactOpen?.();
  }, [isShowingSearchResults, onArtifactMouseDown, onEditArtifactOpen]);

  // Delete with hover state transfer
  const handleDeleteViaRemove = useCallback((artifact: Artifact) => {
    const stableId = getArtifactListId(artifact, isShowingSearchResults);
    const deletedIndex = stableId ? artifacts.findIndex((c) => getArtifactListId(c, isShowingSearchResults) === stableId) : -1;
    onRemove?.(artifact);
    
    // Transfer hover state to next artifact at same position
    if (deletedIndex >= 0) {
      preventEditRef.current = true;
      const nextIndex = deletedIndex < artifacts.length - 1 ? deletedIndex : deletedIndex - 1;
      if (nextIndex >= 0 && nextIndex < artifacts.length - 1) {
        setForceHoverIndex(nextIndex);
      }
      onArtifactDeleted?.(deletedIndex);
    }
  }, [artifacts, isShowingSearchResults, onRemove, onArtifactDeleted]);

  const handleRemove = useCallback((artifact: Artifact) => {
    onRemove?.(artifact);
  }, [onRemove]);

  const handleRevert = useCallback((artifact: Artifact) => {
    onRevert?.(artifact);
  }, [onRevert]);

  // Drag/drop handlers
  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    const target = e.currentTarget;
    const rect = target.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    const after = e.clientY > midY;

    const index = parseInt(target.dataset.index || '0', 10);
    setDragOverIndex(index);
    setDragAfter(after);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOverIndex(null);
    setDragAfter(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    const targetIndex = parseInt(e.currentTarget.dataset.index || '0', 10);

    // File drop
    if (e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      onFileDrop?.(files, targetIndex);
      setDragOverIndex(null);
      setDragAfter(false);
      return;
    }

    // Artifact drop
    const artifactDataStr = e.dataTransfer.getData(DND_MIME);
    if (artifactDataStr) {
      try {
        const dragData: DragData = JSON.parse(artifactDataStr);
        const draggedArtifactIndex = artifacts.findIndex((c) => getArtifactListId(c, isShowingSearchResults) === dragData.artifactId);

        if (draggedArtifactIndex !== -1) {
          // Internal reorder
          let finalIndex = targetIndex;
          if (dragAfter) finalIndex += 1;
          if (draggedArtifactIndex < finalIndex) finalIndex -= 1;

          onReorder?.(dragData.artifactId, finalIndex, dragAfter);
        } else {
          // External artifact drop
          const insertIndex = dragAfter ? targetIndex + 1 : targetIndex;
          onArtifactDrop?.(insertIndex, dragData.ids ?? [dragData.artifactId], {
            sourceType: dragData.sourceType,
            sourceId: dragData.sourceId,
            workspaceId: dragData.sourceWorkspaceId,
            rootIds: dragData.rootIds,
            versionIds: dragData.versionIds,
          });
        }
      } catch (err) {
        console.error('Failed to parse artifact drag data:', err);
      }
    }

    setDragOverIndex(null);
    setDragAfter(false);
  }, [artifacts, dragAfter, isShowingSearchResults, onArtifactDrop, onFileDrop, onReorder]);

  const selectedIdsForDrag = useMemo(() => {
    if (!isSelected) return [] as string[];
    return artifacts
      .map((c) => getArtifactListId(c, isShowingSearchResults))
      .filter((id): id is string => {
        if (!id) return false;
        return isSelected(id);
      });
  }, [artifacts, isSelected, isShowingSearchResults]);

  // Memoize artifact list
  const artifactElements = useMemo(() => {
    const elements: React.ReactNode[] = [];

    artifacts.forEach((artifact, index) => {
      const id = getArtifactListId(artifact, isShowingSearchResults);
      if (!id) return;

      const isThisSelected = isSelected?.(id) ?? false;
      const ids = isThisSelected && selectedIdsForDrag.length > 1
        ? selectedIdsForDrag
        : [id];

      const payload: DragData = {
        type: 'artifact',
        artifactId: id,
        sourceWorkspaceId,
        sourceCollectionId,
        sourceType: sourceWorkspaceId ? 'workspace' : sourceCollectionId ? 'collection' : undefined,
        sourceId: sourceWorkspaceId ?? sourceCollectionId,
        rootIds: ids
          .map((selectedId) => {
            const selectedArtifact = artifacts.find((candidate) => getArtifactListId(candidate, isShowingSearchResults) === selectedId);
            return String(selectedArtifact?.root_id ?? selectedArtifact?.id ?? selectedId);
          })
          .filter(Boolean),
        versionIds: ids
          .map((selectedId) => {
            const selectedArtifact = artifacts.find((candidate) => getArtifactListId(candidate, isShowingSearchResults) === selectedId);
            return String(selectedArtifact?.id ?? '');
          })
          .filter(Boolean),
        timestamp: Date.now(),
        ids,
      };

      const removeLabel = sourceCollectionId ? 'Remove from collection' : 'Remove from workspace';

      elements.push(
        <div
          key={id}
          data-index={index}
          className="relative"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Drop indicator (top or bottom) */}
          {dragOverIndex === index && (
            <div
              className={`absolute ${
                dragAfter ? 'bottom-0' : 'top-0'
              } left-0 right-0 h-0.5 bg-blue-500 z-10`}
            />
          )}

          <CardListItem
            artifact={artifact}
            artifactCount={artifactCountsById[String(artifact.id)] ?? 0}
            selectable={selectable}
            editable={editable}
            draggable={draggable}
            inPanel={inPanel}
            isSelected={isSelected?.(id) ?? false}
            forceHover={forceHoverIndex === index}
            onMouseDown={(e) => onArtifactMouseDown?.(id, e)}
            onEdit={() => handleEdit(artifact)}
            onOpen={onOpenArtifact ? () => onOpenArtifact(artifact) : undefined}
            onRemove={() => (artifact.state === 'draft' ? handleDeleteViaRemove(artifact) : handleRemove(artifact))}
            onRevert={() => handleRevert(artifact)}
            onArchive={!inPanel ? () => onArchive?.(artifact) : undefined}
            onRestore={() => onRestore?.(artifact)}
            onAddToWorkspace={onAddToWorkspace ? () => onAddToWorkspace(artifact) : undefined}
            onAssignCollections={onAssignCollections ? () => onAssignCollections(artifact) : undefined}
            isSearchResult={isShowingSearchResults}
            removeLabel={removeLabel}
            dragData={payload}
          />
        </div>
      );
    });

    return elements;
  }, [
    artifacts,
    sourceWorkspaceId,
    sourceCollectionId,
    selectable,
    editable,
    draggable,
    inPanel,
    isSelected,
    selectedIdsForDrag,
    forceHoverIndex,
    dragOverIndex,
    dragAfter,
    onArtifactMouseDown,
    handleEdit,
    handleDeleteViaRemove,
    handleRemove,
    handleRevert,
    onArchive,
    onRestore,
    onOpenArtifact,
    onAddToWorkspace,
    onAssignCollections,
    isShowingSearchResults,
    artifactCountsById,
    handleDragOver,
    handleDragLeave,
    handleDrop,
  ]);

  return (
    <div
      ref={listRef}
      className="flex flex-col bg-white overflow-y-auto"
      style={{ height: '100%' }}
    >
      {artifactElements}
    </div>
  );
}
