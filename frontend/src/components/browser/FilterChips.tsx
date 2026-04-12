// frontend/src/components/browser/FilterChips.tsx
import { EyeOff, File, FileCode, FileText, Grid3X3, Image, List, Video } from 'lucide-react';
import { useMemo } from 'react';
import { Artifact } from '../../context/workspace/workspace.types';
import { getContentTypeCategory } from '../../utils/search';

type ViewOption = 'grid' | 'list';

interface FilterChipsProps {
  artifacts: Artifact[];
  activeStates: Set<string>;
  activeContentTypes: Set<string>;
  hiddenContentTypes: Set<string>;
  viewMode?: ViewOption;
  onViewModeChange?: (mode: ViewOption) => void;
  onStateToggle: (state: string) => void;
  onContentTypeToggle: (contentType: string) => void;
  onHiddenContentTypeToggle: (contentType: string) => void;
  onClearAll: () => void;
}

function getArtifactContentTypeCategory(artifact: Artifact): string {
  try {
    const context = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
    const ct = context?.content_type || '';
    return getContentTypeCategory(ct);
  } catch {
    return 'unknown';
  }
}

export default function FilterChips({
  artifacts,
  activeStates,
  activeContentTypes,
  hiddenContentTypes,
  viewMode,
  onViewModeChange,
  onStateToggle,
  onContentTypeToggle,
  onHiddenContentTypeToggle,
  onClearAll,
}: FilterChipsProps) {
  // Calculate counts for each state
  const stateCounts = useMemo(() => {
    const counts: Record<string, number> = {
      draft: 0,
      committed: 0,
      archived: 0,
    };

    artifacts.forEach(artifact => {
      if (artifact.state && artifact.state in counts) {
        counts[artifact.state]++;
      }
    });

    return counts;
  }, [artifacts]);
  
  // Calculate counts for each content type
  const contentTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};

    artifacts.forEach(artifact => {
      const category = getArtifactContentTypeCategory(artifact);
      counts[category] = (counts[category] || 0) + 1;
    });

    return counts;
  }, [artifacts]);

  // Get icon for content type
  const getContentTypeIcon = (contentType: string) => {
    switch (contentType) {
      case 'image':
        return <Image className="h-3 w-3" />;
      case 'video':
        return <Video className="h-3 w-3" />;
      case 'pdf':
        return <FileText className="h-3 w-3" />;
      case 'document':
        return <FileCode className="h-3 w-3" />;
      default:
        return <File className="h-3 w-3" />;
    }
  };
  
  // Get display name for content type
  const getContentTypeLabel = (contentType: string) => {
    switch (contentType) {
      case 'image':
        return 'Images';
      case 'video':
        return 'Videos';
      case 'pdf':
        return 'PDFs';
      case 'document':
        return 'Docs';
      default:
        return contentType.charAt(0).toUpperCase() + contentType.slice(1);
    }
  };
  
  // Get color for state
  const getStateColor = (state: string, active: boolean) => {
    if (!active) return 'bg-gray-100 text-gray-600 hover:bg-gray-200';

    switch (state) {
      case 'draft':
        return 'bg-blue-100 text-blue-700 ring-2 ring-blue-300';
      case 'committed':
        return 'bg-green-100 text-green-700 ring-2 ring-green-300';
      case 'archived':
        return 'bg-gray-200 text-gray-700 ring-2 ring-gray-400';
      default:
        return 'bg-gray-100 text-gray-700 ring-2 ring-gray-300';
    }
  };
  
  const states = [
    { key: 'draft', label: 'Draft', count: stateCounts['draft'] },
    { key: 'committed', label: 'Committed', count: stateCounts.committed },
    { key: 'archived', label: 'Archived', count: stateCounts.archived },
  ];
  
  // Sort content types by count (descending)
  const contentTypes = Object.entries(contentTypeCounts)
    .sort(([, a], [, b]) => b - a)
    .filter(([type]) => type !== 'unknown')
    .slice(0, 6) // Show top 6 types
    .map(([type, count]) => ({ key: type, label: getContentTypeLabel(type), count }));

  const hasActiveFilters = activeStates.size > 0 || activeContentTypes.size > 0 || hiddenContentTypes.size > 0;
  const showViewToggle = viewMode !== undefined && onViewModeChange !== undefined;
  
  return (
    <div className="h-10 px-4 bg-gray-100 border-b border-gray-200 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap min-w-0 scrollbar-thin">
        {/* State Filters */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-gray-500 mr-1">State:</span>
          {states.map(state => (
            <button
              key={state.key}
              onClick={() => onStateToggle(state.key)}
              disabled={state.count === 0}
              className={`
                px-2 py-1 text-xs font-medium rounded-full transition-all
                ${state.count === 0 ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
                ${getStateColor(state.key, activeStates.has(state.key))}
              `}
              title={`${state.label}: ${state.count} artifacts`}
            >
              {state.label} <span className="opacity-70">({state.count})</span>
            </button>
          ))}
        </div>
        
        {/* Divider */}
        {contentTypes.length > 0 && (
          <div className="h-4 w-px bg-gray-300" />
        )}
        
        {/* MIME Type Filters */}
        {contentTypes.length > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-gray-500 mr-1">Focus:</span>
            {contentTypes.map(type => (
              <button
                key={type.key}
                onClick={() => onContentTypeToggle(type.key)}
                className={`
                  flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full transition-all
                  ${activeContentTypes.has(type.key)
                    ? 'bg-purple-100 text-purple-700 ring-2 ring-purple-300'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }
                `}
                title={`${type.label}: ${type.count} artifacts`}
              >
                {getContentTypeIcon(type.key)}
                <span>{type.label}</span>
                <span className="opacity-70">({type.count})</span>
              </button>
            ))}
          </div>
        )}

        {contentTypes.length > 0 && (
          <>
            <div className="h-4 w-px bg-gray-300" />
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-gray-500 mr-1">Hide:</span>
              {contentTypes.map(type => (
                <button
                  key={`hidden-${type.key}`}
                  onClick={() => onHiddenContentTypeToggle(type.key)}
                  className={
                    `flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full transition-all ${hiddenContentTypes.has(type.key)
                      ? 'bg-rose-100 text-rose-700 ring-2 ring-rose-300'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`
                  }
                  title={`${hiddenContentTypes.has(type.key) ? 'Show' : 'Hide'} ${type.label}`}
                >
                  <EyeOff className="h-3 w-3" />
                  <span>{type.label}</span>
                </button>
              ))}
            </div>
          </>
        )}
        
        {/* Clear All Filters */}
        {hasActiveFilters && (
          <>
            <div className="h-4 w-px bg-gray-300" />
            <button
              onClick={onClearAll}
              className="px-2 py-1 text-xs font-medium text-gray-600 hover:text-gray-900 transition-colors"
            >
              Clear filters
            </button>
          </>
        )}
      </div>

      {showViewToggle && (
        <div className="flex flex-shrink-0 items-center rounded border border-gray-300 bg-white p-0.5" role="group" aria-label="Workspace view mode">
          <button
            type="button"
            aria-label="Grid view"
            aria-pressed={viewMode === 'grid'}
            onClick={() => onViewModeChange('grid')}
            className={`h-6 w-6 rounded flex items-center justify-center ${viewMode === 'grid' ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}`}
          >
            <Grid3X3 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="List view"
            aria-pressed={viewMode === 'list'}
            onClick={() => onViewModeChange('list')}
            className={`h-6 w-6 rounded flex items-center justify-center ${viewMode === 'list' ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'}`}
          >
            <List className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
