/**
 * BrowserControls
 *
 * Compact toolbar that lets the user switch view mode (grid / list / tree)
 * and sort order. Rendered inside CardBrowser and also re-exported for use
 * in WorkspaceToolbar when the host wants to drive them externally.
 */
import { FiGrid, FiList } from 'react-icons/fi';
import { Trees } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import clsx from 'clsx';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ViewMode = 'grid' | 'list' | 'tree';
export type SortMode = 'recent' | 'title' | 'created' | 'committed' | 'manual';

const VIEW_OPTIONS: { mode: ViewMode; icon: React.ElementType; label: string }[] = [
  { mode: 'grid', icon: FiGrid,  label: 'Grid view' },
  { mode: 'list', icon: FiList,  label: 'List view' },
  { mode: 'tree', icon: Trees,   label: 'Tree view' },
];

const SORT_OPTIONS: { mode: SortMode; label: string }[] = [
  { mode: 'manual',   label: 'Manual order' },
  { mode: 'recent',   label: 'Recently added' },
  { mode: 'title',    label: 'Title (A → Z)' },
  { mode: 'created',  label: 'Date created' },
  { mode: 'committed', label: 'Date modified' },
];

// ─── Component ────────────────────────────────────────────────────────────────

interface BrowserControlsProps {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  sortMode?: SortMode;
  onSortChange?: (mode: SortMode) => void;
  /** Compact=true hides sort and labels, shows only icon buttons. */
  compact?: boolean;
  className?: string;
}

export function BrowserControls({
  viewMode,
  onViewModeChange,
  sortMode,
  onSortChange,
  compact = false,
  className,
}: BrowserControlsProps) {
  const ActiveIcon = VIEW_OPTIONS.find((o) => o.mode === viewMode)?.icon ?? FiGrid;
  const sortLabel = SORT_OPTIONS.find((o) => o.mode === sortMode)?.label;

  return (
    <div className={clsx('flex items-center gap-1', className)}>
      {/* Sort dropdown (hidden in compact mode) */}
      {!compact && onSortChange && sortMode && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="h-7 px-2 text-xs rounded border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 whitespace-nowrap"
              title="Sort"
            >
              {sortLabel ?? 'Sort'}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {SORT_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt.mode}
                onClick={() => onSortChange(opt.mode)}
                className={clsx(sortMode === opt.mode && 'font-semibold')}
              >
                {opt.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* View mode toggle */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="h-7 w-7 inline-flex items-center justify-center rounded border border-gray-200 bg-white hover:bg-gray-50 text-gray-700"
            title="View mode"
          >
            <ActiveIcon size={14} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {VIEW_OPTIONS.map(({ mode, icon: Icon, label }) => (
            <DropdownMenuItem
              key={mode}
              onClick={() => onViewModeChange(mode)}
              className={clsx('flex items-center gap-2', viewMode === mode && 'font-semibold')}
            >
              <Icon size={14} />
              {label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export default BrowserControls;
