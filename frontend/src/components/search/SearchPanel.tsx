/**
 * SearchPanel
 *
 * Left panel. Shows a global search bar (always visible) and renders
 * resolved search-result artifacts via CardBrowser (read-only).
 *
 * Artifact resolution (SearchHit → Artifact) happens in the host (MainLayout).
 * This component is controlled: host supplies `artifacts` after resolving hits.
 *
 * Phase 1: search results only. Pinned view tabs are a future enhancement.
 */
import type { Artifact } from '../../context/workspace/workspace.types';
import type { SearchResponse } from '../../api/types/search';
import AdvancedSearch from '../browser/AdvancedSearch';
import CardGrid from '../common/CardGrid';
import CardList from '../common/CardList';
import { useEffect, useMemo, useState, type MouseEvent } from 'react';
import { getStableArtifactId } from '@/utils/artifact-identifiers';
import { LayoutGrid, List } from 'lucide-react';

type GlobalSearchSourceScope = 'all' | 'collections' | 'workspaces';
type SearchViewMode = 'grid' | 'list';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SearchPanelProps {
  /** Resolved artifacts to display (converted from SearchResponse.hits by host). */
  artifacts: Artifact[];
  /** Whether the host is converting hits (show skeleton). */
  isLoading?: boolean;
  /** Raw search results (passed up to host for artifact resolution). */
  onResults?: (results: SearchResponse) => void;
  /** Called when the search input is cleared. */
  onClear?: () => void;
  /** External clear trigger (increment to programmatically clear the search bar). */
  clearTrigger?: number;
  /** Allow user to add a search result artifact to the active workspace. */
  onAddToWorkspace?: (artifact: Artifact) => void;
  onOpenArtifact?: (artifact: Artifact) => void;
  /** Called when a matched collection is clicked. */
  onCollectionSelect?: (collectionId: string) => void;
  /** Sort/aperture controls (forwarded from MainLayout). */
  sortMode?: 'relevance' | 'recency';
  onSortChange?: (mode: 'relevance' | 'recency') => void;
  aperture?: number;
  onApertureChange?: (value: number) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function SearchPanel({
  artifacts,
  isLoading,
  onResults,
  onClear,
  clearTrigger,
  onAddToWorkspace,
  onOpenArtifact,
  onCollectionSelect,
  sortMode,
  // onSortChange — reserved for when AdvancedSearch gains a sort control
  aperture,
  onApertureChange,
}: SearchPanelProps) {
  void onCollectionSelect;

  const [sourceScope, setSourceScope] = useState<GlobalSearchSourceScope>('all');
  const [viewMode, setViewMode] = useState<SearchViewMode>('grid');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [anchorId, setAnchorId] = useState<string | null>(null);

  const artifactUiId = (artifact: Artifact) => (artifact.root_id ? String(artifact.root_id) : getStableArtifactId(artifact));

  const incomingOrderedIds = useMemo(
    () => artifacts.map((artifact) => artifactUiId(artifact)).filter((id): id is string => Boolean(id)),
    [artifacts],
  );

  const [orderedIds, setOrderedIds] = useState<string[]>(incomingOrderedIds);

  useEffect(() => {
    setOrderedIds((prev) => {
      const incomingSet = new Set(incomingOrderedIds);
      const preserved = prev.filter((id) => incomingSet.has(id));
      const existing = new Set(preserved);
      const appended = incomingOrderedIds.filter((id) => !existing.has(id));
      return [...preserved, ...appended];
    });
  }, [incomingOrderedIds]);

  useEffect(() => {
    setSelectedIds((prev) => prev.filter((id) => orderedIds.includes(id)));
    setAnchorId((prev) => (prev && orderedIds.includes(prev) ? prev : null));
  }, [orderedIds]);

  const idsByAnyArtifactId = useMemo(() => {
    const map = new Map<string, string>();
    artifacts.forEach((artifact) => {
      const uiId = artifactUiId(artifact);
      if (!uiId) return;
      if (artifact.id) map.set(String(artifact.id), uiId);
      if (artifact.root_id) map.set(String(artifact.root_id), uiId);
    });
    return map;
  }, [artifacts]);

  const handleArtifactMouseDown = (id: string, event: MouseEvent) => {
    const normalizedId = idsByAnyArtifactId.get(id) ?? id;
    const isShift = event.shiftKey;
    const isMeta = event.metaKey || event.ctrlKey;

    setSelectedIds((prev) => {
      if (isShift && anchorId) {
        const start = orderedIds.indexOf(anchorId);
        const end = orderedIds.indexOf(normalizedId);
        if (start === -1 || end === -1) return prev;
        const [lo, hi] = start < end ? [start, end] : [end, start];
        const range = orderedIds.slice(lo, hi + 1);
        return Array.from(new Set([...prev, ...range]));
      }

      if (isMeta) {
        setAnchorId(normalizedId);
        return prev.includes(normalizedId)
          ? prev.filter((existing) => existing !== normalizedId)
          : [...prev, normalizedId];
      }

      setAnchorId(normalizedId);
      return [normalizedId];
    });
  };

  const isArtifactSelected = (id: string) => selectedIds.includes(id);

  const handleListReorder = (artifactId: string, targetIndex: number) => {
    const normalized = idsByAnyArtifactId.get(artifactId) ?? artifactId;
    setOrderedIds((prev) => {
      const from = prev.indexOf(normalized);
      if (from === -1) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      const clamped = Math.max(0, Math.min(targetIndex, next.length));
      next.splice(clamped, 0, moved);
      return next;
    });
  };

  const orderedArtifacts = useMemo(() => {
    const map = new Map<string, Artifact>();
    artifacts.forEach((artifact) => {
      const id = artifactUiId(artifact);
      if (id) map.set(id, artifact);
    });
    return orderedIds.map((id) => map.get(id)).filter((artifact): artifact is Artifact => Boolean(artifact));
  }, [artifacts, orderedIds]);

  const hasResults = orderedArtifacts.length > 0;
  const resultsBgClass = 'bg-blue-50';

  return (
    <div className="flex flex-col h-full bg-blue-50">
      {/* Search bar — always visible */}
      <div className="flex-shrink-0 px-3 h-14 flex items-center border-b border-gray-200 bg-white">
        <AdvancedSearch
          scope="global"
          scopeId=""
          globalSourceScope={sourceScope}
          placeholder="Find something..."
          onResults={onResults}
          onClear={onClear}
          clearTrigger={clearTrigger}
          sortMode={sortMode}
          onApertureChange={onApertureChange}
          aperture={aperture}
          compact
          enableSuggestions
        />
      </div>

      {/* Result count row */}
      <div className="flex-shrink-0 h-10 px-3 flex items-center justify-between text-xs text-gray-500 border-b border-gray-200 bg-gray-100 gap-2">
        <div>{hasResults ? `${orderedArtifacts.length} result${orderedArtifacts.length !== 1 ? 's' : ''}` : null}</div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-gray-600 whitespace-nowrap">
            <span>Search in</span>
            <select
              aria-label="Search source scope"
              value={sourceScope}
              onChange={(e) => setSourceScope(e.target.value as GlobalSearchSourceScope)}
              className="h-7 rounded border border-gray-300 bg-white px-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              <option value="all">All</option>
              <option value="collections">Collections</option>
              <option value="workspaces">Workspaces</option>
            </select>
          </label>

          <div className="flex items-center rounded border border-gray-300 bg-white p-0.5" role="group" aria-label="Search result view mode">
            <button
              type="button"
              aria-label="Grid view"
              aria-pressed={viewMode === 'grid'}
              onClick={() => setViewMode('grid')}
              className={`h-6 w-6 rounded flex items-center justify-center ${viewMode === 'grid' ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}`}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              aria-label="List view"
              aria-pressed={viewMode === 'list'}
              onClick={() => setViewMode('list')}
              className={`h-6 w-6 rounded flex items-center justify-center ${viewMode === 'list' ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}`}
            >
              <List className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Results / empty state */}
      <div className={`flex-1 overflow-y-auto ${resultsBgClass}`}>
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">
            Searching…
          </div>
        ) : hasResults ? (
          viewMode === 'grid' ? (
            <div className="px-3 pt-3 pb-4">
              <CardGrid
                artifacts={orderedArtifacts}
                selectable
                draggable
                fillHeight
                isShowingSearchResults
                selectedIds={selectedIds}
                isSelected={isArtifactSelected}
                onArtifactMouseDown={handleArtifactMouseDown}
                onOpenArtifact={onOpenArtifact}
                onAddToWorkspace={onAddToWorkspace}
              />
            </div>
          ) : (
            <div className="h-full px-3 pb-3 pt-2">
              <CardList
                artifacts={orderedArtifacts}
                selectable
                draggable
                isShowingSearchResults
                isSelected={(id) => isArtifactSelected(idsByAnyArtifactId.get(id) ?? id)}
                onArtifactMouseDown={(id, e) => handleArtifactMouseDown(id, e as MouseEvent)}
                onOpenArtifact={onOpenArtifact}
                onAddToWorkspace={onAddToWorkspace}
                onReorder={handleListReorder}
              />
            </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center h-full px-4 text-center text-sm text-gray-400 gap-2">
            <p className="font-medium text-gray-500">Nothing Here</p>
            <p className="text-xs">
              Use the search bar above to find artifacts across your workspaces and collections.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default SearchPanel;
