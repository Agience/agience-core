/**
 * CardBrowser
 *
 * Universal artifact list renderer. A control, not a page.
 * Hosts (WorkspacePanel, SearchPanel, ViewCardViewer) supply artifacts and
 * list-management callbacks; CardBrowser handles layout and delegation.
 *
 * Delegates to:
 *   - CardGrid   (viewMode="grid")
 *   - CardList   (viewMode="list")
 *   - CardTreeItem[] flat list (viewMode="tree", phase 1)
 *
 * CardBrowser does NOT own: add, delete, bulk ops — those belong to the host.
 */
import CardGrid from './CardGrid';
import CardList from './CardList';
import { CardTreeItem } from './CardTreeItem';
import type { Artifact } from '../../context/workspace/workspace.types';
import type { ActiveSource } from '../../types/workspace';
import { getStableArtifactId } from '@/utils/artifact-identifiers';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ArtifactBrowserViewMode = 'grid' | 'list' | 'tree';

export interface CardBrowserProps {
  artifacts: Artifact[];

  // ── Layout ────────────────────────────────────────────────────────────────
  viewMode?: ArtifactBrowserViewMode;
  /** Called when the user changes view mode via embedded BrowserControls. */
  onViewModeChange?: (mode: ArtifactBrowserViewMode) => void;

  // ── Capabilities ─────────────────────────────────────────────────────────
  selectable?: boolean;
  draggable?: boolean;
  editable?: boolean;
  /** When true: no add/delete/drag ops exposed (read-only display). */
  readOnly?: boolean;
  /** Fill available height in grid mode. */
  fillHeight?: boolean;

  // ── Selection ─────────────────────────────────────────────────────────────
  selectedIds?: string[];
  isSelected?: (id: string) => boolean;
  onArtifactMouseDown?: (id: string, e: React.MouseEvent | React.DragEvent) => void;

  // ── Source context (for CardGrid) ─────────────────────────────────────────
  activeSource?: ActiveSource;
  isShowingSearchResults?: boolean;

  // ── Artifact events ───────────────────────────────────────────────────────────
  onOpenArtifact?: (artifact: Artifact) => void;
  onRemove?: (artifact: Artifact) => void;
  onRevert?: (artifact: Artifact) => void;
  onArchive?: (artifact: Artifact) => void;
  onRestore?: (artifact: Artifact) => void;
  onAddToWorkspace?: (artifact: Artifact) => void;
  onAssignCollections?: (artifact: Artifact) => void;

  // ── Order / DnD ───────────────────────────────────────────────────────────
  /** Called with re-ordered array of artifact IDs after a drag-reorder. */
  onOrder?: (ids: string[]) => void;
  onFileDrop?: (index: number, files: File[]) => void;
  onArtifactDrop?: (
    index: number,
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
  /** @deprecated Use onArtifactDrop */
  onEditArtifactOpen?: () => void;
  externalTailHover?: 'file' | 'artifacts' | null;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CardBrowser({
  artifacts,
  viewMode: viewModeProp,
  selectable = false,
  draggable = false,
  editable = true,
  readOnly = false,
  fillHeight,
  selectedIds,
  isSelected,
  onArtifactMouseDown,
  activeSource,
  isShowingSearchResults = false,
  onOpenArtifact,
  onRemove,
  onRevert,
  onArchive,
  onRestore,
  onAddToWorkspace,
  onAssignCollections,
  onOrder,
  onFileDrop,
  onArtifactDrop,
  onEditArtifactOpen,
  externalTailHover,
}: CardBrowserProps) {
  const viewMode = viewModeProp ?? 'grid';

  // ── Tree view ──────────────────────────────────────────────────────────────
  if (viewMode === 'tree') {
    return (
      <div className="flex flex-col w-full overflow-y-auto">
        {artifacts.map((artifact) => {
          const id = getStableArtifactId(artifact);
          return (
            <CardTreeItem
              key={id ?? artifact.id}
              artifact={artifact}
              isSelected={id ? (isSelected?.(id) ?? false) : false}
              onMouseDown={id ? (e) => onArtifactMouseDown?.(id, e) : undefined}
              onOpen={onOpenArtifact}
              onRemove={readOnly ? undefined : onRemove}
              onRevert={readOnly ? undefined : onRevert}
              onArchive={readOnly ? undefined : onArchive}
              onRestore={readOnly ? undefined : onRestore}
            />
          );
        })}
      </div>
    );
  }

  // ── List view ──────────────────────────────────────────────────────────────
  if (viewMode === 'list') {
    return (
      <CardList
        artifacts={artifacts}
        selectable={selectable}
        draggable={!readOnly && draggable}
        editable={!readOnly && editable}
        isSelected={isSelected}
        onArtifactMouseDown={onArtifactMouseDown}
        onOpenArtifact={onOpenArtifact}
        onRemove={readOnly ? undefined : onRemove}
        onRevert={readOnly ? undefined : onRevert}
        onArchive={readOnly ? undefined : onArchive}
        onRestore={readOnly ? undefined : onRestore}
        onAddToWorkspace={onAddToWorkspace}
        isShowingSearchResults={isShowingSearchResults}
        onFileDrop={readOnly || !onFileDrop ? undefined : (files, index) => onFileDrop(index ?? 0, files)}
        onArtifactDrop={readOnly ? undefined : onArtifactDrop}
        onReorder={
          onOrder
            ? (artifactId, targetIndex) => {
                // Convert index-based reorder to ID-array for onOrder
                const newOrder = [...artifacts];
                const fromIndex = newOrder.findIndex(
                  (c) => getStableArtifactId(c) === artifactId,
                );
                if (fromIndex !== -1) {
                  const [moved] = newOrder.splice(fromIndex, 1);
                  newOrder.splice(targetIndex, 0, moved);
                  onOrder(newOrder.map((c) => String(c.id ?? '')));
                }
              }
            : undefined
        }
        onEditArtifactOpen={onEditArtifactOpen}
      />
    );
  }

  // ── Grid view (default) ────────────────────────────────────────────────────
  return (
    <CardGrid
      artifacts={artifacts}
      selectable={selectable}
      draggable={!readOnly && draggable}
      editable={!readOnly && editable}
      fillHeight={fillHeight}
      selectedIds={selectedIds}
      isSelected={isSelected}
      activeSource={activeSource}
      isShowingSearchResults={isShowingSearchResults}
      onArtifactMouseDown={onArtifactMouseDown}
      onOpenArtifact={onOpenArtifact}
      onRemove={readOnly ? undefined : onRemove}
      onRevert={readOnly ? undefined : onRevert}
      onAddToWorkspace={onAddToWorkspace}
      onAssignCollections={readOnly ? undefined : onAssignCollections}
      onOrder={readOnly ? undefined : onOrder}
      onFileDrop={readOnly ? undefined : onFileDrop}
      onArtifactDrop={readOnly ? undefined : onArtifactDrop}
      onEditArtifactOpen={onEditArtifactOpen}
      externalTailHover={externalTailHover}
    />
  );
}

export default CardBrowser;
