// src/components/palette/InputPanel.tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { usePalette } from '../../../hooks/usePalette';
import { useWorkspace } from '../../../hooks/useWorkspace';
import CardGrid from '../../common/CardGrid';
import { Artifact } from '../../../context/workspace/workspace.types';
import { getAgienceDragPayload, getDroppedArtifactIds, isAgienceDrag } from '../../../dnd/agienceDrag';

export default function InputPanel() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.input;
  const { artifacts: workspaceArtifacts, selectedArtifactIds, selectArtifact } = useWorkspace();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [dragDepth, setDragDepth] = useState(0);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  // Sync panel artifacts when workspace artifacts change
  useEffect(() => {
    updatePanelData('input', (prev) => {
      const updatedArtifacts = prev.artifacts.map(panelArtifact => {
        const workspaceArtifact = workspaceArtifacts.find(wc => String(wc.id) === String(panelArtifact.id));
        return workspaceArtifact || panelArtifact;
      });
      return { ...prev, artifacts: updatedArtifacts };
    });
  }, [workspaceArtifacts, updatePanelData]);

  // Only check for artifact drags - NO file drags
  const isArtifactsDrag = (dt: DataTransfer | null | undefined) => {
    return isAgienceDrag(dt);
  };

  // Add artifacts from workspace to panel
  const addArtifactsFromWorkspace = useCallback(
    (ids: string[]) => {
      if (!ids.length) return;

      updatePanelData('input', (prev) => {
        const existingIds = new Set(prev.artifacts.map((c) => String(c.id)));
        const artifactsToAdd = ids
          .map(id => workspaceArtifacts.find(c => String(c.id) === String(id)))
          .filter((artifact): artifact is Artifact => !!artifact && !existingIds.has(String(artifact.id)));
        
        if (artifactsToAdd.length === 0) return prev;
        return { ...prev, artifacts: [...prev.artifacts, ...artifactsToAdd] };
      });
    },
    [workspaceArtifacts, updatePanelData]
  );

  const removeArtifactAtIndex = useCallback((index: number) => {
    updatePanelData('input', (prev) => {
      const updated = [...prev.artifacts];
      updated.splice(index, 1);
      return { ...prev, artifacts: updated };
    });
  }, [updatePanelData]);

  const handleReorder = useCallback((orderedIds: string[]) => {
    updatePanelData('input', (prev) => {
      const byId = new Map(prev.artifacts.map((c) => [String(c.id), c]));
      const reordered = orderedIds.map(id => byId.get(id)).filter(Boolean) as Artifact[];
      return { ...prev, artifacts: reordered };
    });
  }, [updatePanelData]);

  // NEW: Handle drops on CardGrid - distinguish workspace vs panel artifacts
  const handleArtifactDrop = useCallback((insertIndex: number, draggedIds: string[]) => {
    const panelIds = new Set(panelState.artifacts.map(c => String(c.id)));
    const fromWorkspace = draggedIds.filter(id => !panelIds.has(id));
    
    if (fromWorkspace.length > 0) {
      // New artifacts from workspace - insert at position
      updatePanelData('input', (prev) => {
        const existingIds = new Set(prev.artifacts.map((c) => String(c.id)));
        const artifactsToAdd = fromWorkspace
          .map(id => workspaceArtifacts.find(c => String(c.id) === String(id)))
          .filter((artifact): artifact is Artifact => !!artifact && !existingIds.has(String(artifact.id)));
        
        if (artifactsToAdd.length === 0) {
          return prev;
        }
        
        // Insert at the specified index
        const updated = [...prev.artifacts];
        updated.splice(insertIndex, 0, ...artifactsToAdd);
        return { ...prev, artifacts: updated };
      });
    }
    // Reordering is handled by onOrder callback, not here
  }, [panelState.artifacts, workspaceArtifacts, updatePanelData]);

  const parseDragIds = useCallback((e: React.DragEvent): string[] => {
    return getDroppedArtifactIds(e.dataTransfer);
  }, []);

  // Background drop handlers - only used when panel is EMPTY
  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!isArtifactsDrag(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    setDragDepth(prev => prev + 1);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    if (!isArtifactsDrag(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    setDragDepth(prev => Math.max(prev - 1, 0));
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (!isArtifactsDrag(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (!isArtifactsDrag(e.dataTransfer)) return;
      
      e.preventDefault();
      e.stopPropagation();
      setDragDepth(0);

      const payload = getAgienceDragPayload(e.dataTransfer);
      if (payload?.kind === 'prompt' && payload.body) {
        updatePanelData('input', (prev) => ({
          ...prev,
          text: prev.text ? `${prev.text}\n\n${payload.body}` : payload.body ?? '',
        }));
        return;
      }

      if (payload?.kind === 'text' && payload.text) {
        updatePanelData('input', (prev) => ({
          ...prev,
          text: prev.text ? `${prev.text}\n${payload.text}` : payload.text,
        }));
        return;
      }

      const ids = parseDragIds(e);
      if (ids.length > 0) {
        addArtifactsFromWorkspace(ids);
      }
    },
    [parseDragIds, addArtifactsFromWorkspace, updatePanelData]
  );

  const panelArtifacts = panelState.artifacts.map(artifact => ({
    ...artifact,
    state: artifact.state ?? 'committed',
  })) as Artifact[];

  const handlePanelClick = (e: React.MouseEvent) => {
    // Don't focus textarea if clicking on artifacts or if edit modal is open
    const target = e.target as Element;
    const clickedOnArtifact = target.closest('[data-role="artifact-grid"]');
    
    if (!clickedOnArtifact && !isEditModalOpen) {
      textareaRef.current?.focus();
    }
  };

  const handleEditOpen = () => setIsEditModalOpen(true);
  const handleEditClose = () => setIsEditModalOpen(false);

  return (
    <div className="flex flex-col h-full max-h-full">
      <div
        onClick={handlePanelClick}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        className={`flex flex-col flex-1 min-h-0 w-full rounded bg-white overflow-hidden focus-within:ring-2 focus-within:ring-blue-500 ${
          dragDepth > 0 ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-300'
        }`}
      >
        {/* Artifact grid - scrollable container, NO padding on wrapper */}
        {panelArtifacts.length > 0 && (
          <div className="overflow-auto flex-1 min-h-0 pb-0">
            <CardGrid
              artifacts={panelArtifacts}
              selectable
              draggable={true}
              editable
              inPanel
              fillHeight={false}
              selectedIds={selectedArtifactIds}
              isSelected={(id) => selectedArtifactIds.includes(String(id))}
              onArtifactMouseDown={(id, e) => selectArtifact(String(id), e)}
              onRemove={(artifact) => {
                const index = panelArtifacts.findIndex(c => String(c.id) === String(artifact.id));
                if (index !== -1) removeArtifactAtIndex(index);
              }}
              onOrder={handleReorder}
              onArtifactDrop={handleArtifactDrop}
              onEditArtifactOpen={handleEditOpen}
              onEditArtifactClose={handleEditClose}
            />
          </div>
        )}

        {/* Textarea always visible at bottom - minimal height, minimal padding */}
        <textarea
          ref={textareaRef}
          className="w-full border-none outline-none bg-transparent resize-none px-2 flex-shrink-0"
          style={{ minHeight: '2.5rem', paddingTop: '0.25rem', paddingBottom: '0.25rem' }}
          placeholder="Anything…"
          value={panelState.text}
          onChange={(e) =>
            updatePanelData('input', (prev) => ({
              ...prev,
              text: e.target.value,
            }))
          }
          onFocus={(e) => e.stopPropagation()}
        />
      </div>
    </div>
  );
}