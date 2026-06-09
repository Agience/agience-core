/**
 * WorkspaceToolbar
 *
 * Top toolbar for WorkspacePanel. Contains:
 *   - WorkspaceTabs (left side)
 *   - View mode + sort controls via BrowserControls
 *   - New Artifact button
 *   - Review Changes button with pending-count badge
 *   - Source context label (collection name / search results)
 *
 * Replaces BrowserHeader + ControlsBar combination.
 */
import { useEffect, useState } from 'react';
import { FiPlus, FiSave } from 'react-icons/fi';
import { FolderOpen, Loader2, Upload } from 'lucide-react';
import { WorkspaceTabs } from './WorkspaceTabs';
import { BrowserControls } from '../common/BrowserControls';
import type { ArtifactBrowserViewMode } from '../common/CardBrowser';
import type { SortMode } from '../common/BrowserControls';
import type { ActiveSource } from '../../types/workspace';
import { useWorkspace } from '../../hooks/useWorkspace';
import type { CollectionResponse } from '../../api/types';
import { listCollections } from '../../api/collections';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface WorkspaceToolbarProps {
  activeSource: ActiveSource;
  viewMode: ArtifactBrowserViewMode;
  onViewModeChange: (mode: ArtifactBrowserViewMode) => void;
  sortMode?: SortMode;
  onSortChange?: (mode: SortMode) => void;
  isShowingSearchResults?: boolean;
  /** Number of uncommitted changes (new + modified + archived). */
  pendingChangeCount?: number;
  onReviewChanges?: () => void;
  isReviewLoading?: boolean;
  isCommitting?: boolean;
  canReview?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function WorkspaceToolbar({
  activeSource,
  viewMode,
  onViewModeChange,
  sortMode,
  onSortChange,
  isShowingSearchResults = false,
  pendingChangeCount = 0,
  onReviewChanges,
  isReviewLoading = false,
  isCommitting = false,
  canReview = false,
}: WorkspaceToolbarProps) {
  const { createNewArtifact, createArtifact } = useWorkspace();
  const [collections, setCollections] = useState<CollectionResponse[]>([]);

  // Lazily load collection names for the "Save View" feature
  useEffect(() => {
    listCollections().then(setCollections).catch(console.error);
  }, []);

  const canSaveView =
    !isShowingSearchResults && activeSource?.type === 'collection';

  const handleSaveView = async () => {
    if (!canSaveView) return;
    const collectionId = activeSource.id;
    const collection = collections.find((c) => c.id === collectionId);
    const name = collection?.name || 'Collection';
    await createArtifact({
      content: '',
      context: JSON.stringify({
        mime: 'application/vnd.agience.view+json',
        title: `${name} view`,
        target: { kind: 'collection', id: collectionId },
      }),
    });
  };

  return (
    <div className="border-b border-gray-200 bg-white flex-shrink-0">
      {/* Main row: tabs + controls */}
      <div className="flex items-center justify-between pl-[10px] pr-4 h-14 gap-2">
        {/* Left: workspace tabs */}
        <div className="flex-1 min-w-0 overflow-hidden">
          <WorkspaceTabs />
        </div>

        {/* Right: controls */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {/* View + sort controls */}
          <BrowserControls
            viewMode={viewMode}
            onViewModeChange={onViewModeChange}
            sortMode={sortMode}
            onSortChange={onSortChange}
          />

          {/* New Artifact (workspace only) */}
          {!isShowingSearchResults && activeSource?.type === 'workspace' && (
            <button
              type="button"
              onClick={createNewArtifact}
              className="h-7 w-7 inline-flex items-center justify-center rounded bg-purple-600 text-white hover:bg-purple-700 transition-colors"
              title="New card"
            >
              <FiPlus size={14} />
            </button>
          )}

          {/* Save as View artifact (collection source) */}
          {canSaveView && (
            <button
              type="button"
              onClick={handleSaveView}
              className="h-7 w-7 inline-flex items-center justify-center rounded border border-teal-500 text-teal-700 hover:bg-teal-50 transition-colors"
              title="Save this collection view as a View artifact"
            >
              <FiSave size={14} />
            </button>
          )}

          {/* Review / Commit */}
          {!isShowingSearchResults && (
            <button
              type="button"
              onClick={onReviewChanges}
              disabled={isCommitting || isReviewLoading || !onReviewChanges || !canReview}
              className="relative h-7 w-7 inline-flex items-center justify-center rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
              title={
                isReviewLoading || isCommitting
                  ? 'Processing…'
                  : 'Review and commit changes'
              }
            >
              {pendingChangeCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[16px] px-0.5 rounded-full bg-blue-500 text-[9px] leading-tight text-white font-semibold flex items-center justify-center shadow-sm">
                  {pendingChangeCount}
                </span>
              )}
              {isReviewLoading || isCommitting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Source context label (below tabs) */}
      <div className="flex items-center px-4 pb-1.5 text-[11px] text-muted-foreground gap-2 min-h-[18px]">
        {isShowingSearchResults && (
          <>
            <FolderOpen size={12} className="text-purple-600" />
            <span className="font-medium text-purple-700">Search results</span>
          </>
        )}
        {!isShowingSearchResults && activeSource?.type === 'collection' && (
          <>
            <FolderOpen size={12} className="text-blue-500" />
            <span className="text-blue-700 truncate">
              {collections.find((c) => c.id === activeSource.id)?.name ||
                'Collection'}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

export default WorkspaceToolbar;
