/**
 * WorkspaceGrid – workspace-level Artifact Grid / desktop surface inside the Browser.
 *
 * Features:
 * - Artifact ordering (drag to reorder)
 * - Single/multi-select
 * - Double-click to open Artifact Floating windows (containers show children, leaves show editor)
 * - Desktop layout mode (free positioning with empty spaces)
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useWorkspace } from '@/hooks/useWorkspace';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import CardGrid from '@/components/common/CardGrid';
import { CardGridItem } from '@/components/common/CardGridItem';
import { Artifact } from '@/context/workspace/workspace.types';
import FloatingCardWindow from '@/components/windows/FloatingCardWindow';
import { 
  loadDesktopLayout, 
  saveDesktopLayout, 
  getDefaultArtifactPosition,
  type LayoutMode,
  type ArtifactPosition 
} from '@/utils/desktop-layout';
import { FiGrid, FiLayout } from 'react-icons/fi';

export default function WorkspaceGrid() {
  const { artifacts, selectedArtifactIds, selectArtifact, orderArtifacts, removeArtifact, revertArtifact, updateArtifact, importArtifactsByRootIds } = useWorkspace();
  const { activeWorkspace } = useWorkspaces();
  const [openFloatingArtifacts, setOpenFloatingArtifacts] = useState<string[]>([]);
  
  // Desktop layout state
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('flow');
  const [artifactPositions, setArtifactPositions] = useState<Record<string, ArtifactPosition>>({});

  // Load desktop layout from localStorage on mount
  useEffect(() => {
    if (!activeWorkspace?.id) return;
    const saved = loadDesktopLayout(activeWorkspace.id);
    if (saved) {
      setLayoutMode(saved.mode);
      setArtifactPositions(saved.positions);
    }
  }, [activeWorkspace?.id]);

  // Save desktop layout to localStorage when mode or positions change
  useEffect(() => {
    if (!activeWorkspace?.id) return;
    saveDesktopLayout(activeWorkspace.id, {
      mode: layoutMode,
      positions: artifactPositions,
    });
  }, [activeWorkspace?.id, layoutMode, artifactPositions]);

  // Ensure all artifacts have positions (assign defaults for new artifacts)
  useEffect(() => {
    if (layoutMode !== 'desktop') return;
    
    const missingArtifacts = artifacts.filter(c => c.id && !artifactPositions[String(c.id)]);
    if (missingArtifacts.length === 0) return;

    const newPositions = { ...artifactPositions };
    missingArtifacts.forEach(artifact => {
      if (!artifact.id) return;
      const id = String(artifact.id);
      newPositions[id] = getDefaultArtifactPosition(newPositions, 180, 16);
    });
    setArtifactPositions(newPositions);
  }, [artifacts, artifactPositions, layoutMode]);

  const handleArtifactDoubleClick = useCallback((artifact: Artifact) => {
    if (!artifact.id) return;
    const artifactId = String(artifact.id);
    
    // Open floating window
    setOpenFloatingArtifacts(prev => {
      if (prev.includes(artifactId)) {
        // Already open, bring to front
        return [...prev.filter(id => id !== artifactId), artifactId];
      }
      return [...prev, artifactId];
    });
  }, []);

  const closeFloatingArtifact = useCallback((artifactId: string) => {
    setOpenFloatingArtifacts(prev => prev.filter(id => id !== artifactId));
  }, []);

  const focusFloatingArtifact = useCallback((artifactId: string) => {
    setOpenFloatingArtifacts(prev => {
      if (!prev.includes(artifactId)) return prev;
      return [...prev.filter(id => id !== artifactId), artifactId];
    });
  }, []);

  const handleToggleLayout = useCallback(() => {
    setLayoutMode(prev => prev === 'flow' ? 'desktop' : 'flow');
  }, []);

  const handleArtifactDragEnd = useCallback((artifactId: string, x: number, y: number) => {
    if (layoutMode !== 'desktop') return;
    setArtifactPositions(prev => ({
      ...prev,
      [artifactId]: { x, y },
    }));
  }, [layoutMode]);

  const handleRemoveArtifact = useCallback(async (artifact: Artifact) => {
    if (!artifact.id) return;
    await removeArtifact(String(artifact.id));
  }, [removeArtifact]);

  const handleRevertArtifact = useCallback(async (artifact: Artifact) => {
    if (!artifact.id) return;
    await revertArtifact(String(artifact.id));
  }, [revertArtifact]);

  const handleArchiveArtifact = useCallback(async (artifact: Artifact) => {
    if (!artifact.id) return;
    await updateArtifact({ id: String(artifact.id), state: 'archived' });
  }, [updateArtifact]);

  const handleRestoreArtifact = useCallback(async (artifact: Artifact) => {
    if (!artifact.id) return;
    await updateArtifact({ id: String(artifact.id), state: 'committed' });
  }, [updateArtifact]);

  // Desktop mode: render artifacts with absolute positioning
  type DesktopCard = { artifact: Artifact; pos: ArtifactPosition; isSelected: boolean; id: string };

  const desktopArtifacts = useMemo<DesktopCard[] | null>(() => {
    if (layoutMode !== 'desktop') return null;
    
    const mapped = artifacts.map((artifact): DesktopCard | null => {
      if (!artifact.id) return null;
      const id = String(artifact.id);
      const pos = artifactPositions[id] || { x: 0, y: 0 };
      const isSelected = selectedArtifactIds.includes(id);
      
      return { artifact, pos, isSelected, id };
    }).filter((v): v is DesktopCard => v !== null);

    return mapped;
  }, [layoutMode, artifacts, artifactPositions, selectedArtifactIds]);

  if (artifacts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <p className="text-lg font-medium">Empty workspace</p>
          <p className="text-sm">Add cards to get started</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Layout mode toggle */}
      <div className="absolute top-4 right-4 z-10">
        <button
          onClick={handleToggleLayout}
          className="flex items-center gap-2 px-3 py-2 bg-gradient-to-br from-purple-400/20 via-pink-400/20 to-blue-400/20 hover:from-purple-500/30 hover:via-pink-500/30 hover:to-blue-500/30 border border-purple-200/40 rounded-lg shadow-sm transition-all text-sm font-medium text-purple-700"
          title={layoutMode === 'flow' ? 'Switch to desktop layout' : 'Switch to flow layout'}
        >
          {layoutMode === 'flow' ? (
            <>
              <FiLayout className="w-4 h-4" />
              <span>Desktop</span>
            </>
          ) : (
            <>
              <FiGrid className="w-4 h-4" />
              <span>Flow</span>
            </>
          )}
        </button>
      </div>

      <div className="h-full w-full overflow-auto p-6">
        {layoutMode === 'flow' ? (
          <CardGrid
            artifacts={artifacts}
            selectable
            draggable
            fillHeight={true}
            selectedIds={selectedArtifactIds}
            isSelected={(id) => selectedArtifactIds.includes(id)}
            activeSource={{ type: 'workspace', id: activeWorkspace?.id ?? '' }}
            onArtifactMouseDown={(id, e) => selectArtifact(id, e)}
            onOpenArtifact={(artifact) => handleArtifactDoubleClick(artifact)}
            onOrder={(ids) => orderArtifacts(ids)}
            onArtifactDrop={(insertIndex, draggedIds) => importArtifactsByRootIds(draggedIds, insertIndex)}
          />
        ) : (
          <div className="relative min-h-full" style={{ minWidth: '1200px', minHeight: '800px' }}>
            {desktopArtifacts?.map(({ artifact, pos, isSelected, id }) => (
              <div
                key={id}
                className="absolute"
                style={{
                  left: `${pos.x}px`,
                  top: `${pos.y}px`,
                  width: '180px',
                }}
                onDragEnd={(e) => {
                  const parentRect = e.currentTarget.parentElement?.getBoundingClientRect();
                  if (!parentRect) return;
                  const x = e.clientX - parentRect.left - 90; // center offset (half of 180px)
                  const y = e.clientY - parentRect.top - 90;
                  handleArtifactDragEnd(id, Math.max(0, x), Math.max(0, y));
                }}
              >
                <CardGridItem
                  artifact={artifact}
                  draggable
                  selectable
                  isSelected={isSelected}
                  onMouseDown={(e) => selectArtifact(id, e)}
                  onOpen={(artifact) => handleArtifactDoubleClick(artifact)}
                  onRemove={handleRemoveArtifact}
                  onRevert={handleRevertArtifact}
                  onArchive={handleArchiveArtifact}
                  onRestore={handleRestoreArtifact}
                  dragData={{ ids: selectedArtifactIds.length > 0 ? selectedArtifactIds : [id] }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Floating windows */}
      {openFloatingArtifacts.map((artifactId, idx) => (
        <FloatingCardWindow
          key={artifactId}
          artifactId={artifactId}
          zIndex={1000 + idx}
          onClose={() => closeFloatingArtifact(artifactId)}
          onFocus={() => focusFloatingArtifact(artifactId)}
        />
      ))}
    </>
  );
}
