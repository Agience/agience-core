import clsx from 'clsx';
import { FiChevronDown, FiCheck, FiGrid, FiList, FiLayers } from 'react-icons/fi';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

type ArtifactState = 'all' | 'draft' | 'committed' | 'archived';
type SortOption = 'recent' | 'title' | 'created' | 'committed' | 'manual';
type ViewOption = 'grid' | 'list' | 'compact';

interface FilterBarProps {
  counts: {
    total: number;
    new: number;
    modified: number;
    archived: number;
  };
  activeFilter: ArtifactState;
  onFilterChange: (filter: ArtifactState) => void;
  sortBy: SortOption;
  onSortChange: (sort: SortOption) => void;
  viewMode: ViewOption;
  onViewChange: (view: ViewOption) => void;
  isOpen: boolean;
}

export default function FilterBar({ 
  counts, 
  activeFilter, 
  onFilterChange,
  sortBy,
  onSortChange,
  viewMode,
  onViewChange,
  isOpen
}: FilterBarProps) {
  const filters: { key: ArtifactState; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: counts.total },
    { key: 'draft', label: 'New', count: counts.new },
    { key: 'committed', label: 'Modified', count: counts.modified },
    { key: 'archived', label: 'Archived', count: counts.archived },
  ];

  const sortOptions = [
    { value: 'recent' as const, label: 'Recent' },
    { value: 'title' as const, label: 'Title' },
    { value: 'created' as const, label: 'Created' },
    { value: 'committed' as const, label: 'Modified' },
    { value: 'manual' as const, label: 'Manual Order' },
  ];

  const viewOptions = [
    { value: 'grid' as const, label: 'Grid', icon: FiGrid },
    { value: 'list' as const, label: 'List', icon: FiList },
    { value: 'compact' as const, label: 'Compact', icon: FiLayers },
  ];

  return (
    <div 
      className={clsx(
        "flex items-center justify-between px-6 pr-2 bg-white border-b border-gray-200 overflow-hidden transition-all duration-300 ease-in-out",
        isOpen ? "max-h-20 opacity-100 py-2" : "max-h-0 opacity-0 border-b-0"
      )}
    >
      {/* Left: Filter Buttons */}
      <div className="flex items-center gap-1">
        {filters.map((filter) => {
          // Get color for each filter type when selected
          const getSelectedColor = () => {
            switch (filter.key) {
              case 'all': return 'bg-primary-600 text-white';
              case 'draft': return 'bg-green-500 text-white';
              case 'committed': return 'bg-amber-500 text-white';
              case 'archived': return 'bg-red-500 text-white';
              default: return 'bg-gray-400 text-white';
            }
          };
          
          return (
            <button
              key={filter.key}
              onClick={() => onFilterChange(filter.key)}
              className={clsx(
                'flex items-center gap-1.5 px-2 py-1 rounded text-sm font-medium transition-all',
                activeFilter === filter.key
                  ? getSelectedColor()
                  : 'text-gray-600 hover:bg-gray-100'
              )}
            >
              {filter.label}
              {filter.count > 0 && (
                <span className={clsx(
                  'ml-1 px-1.5 py-0.5 rounded-full text-xs',
                  activeFilter === filter.key
                    ? 'bg-white/20'
                    : 'bg-gray-200'
                )}>
                  {filter.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Right: Sort and View */}
      <div className="flex items-center gap-2">
        {/* Sort Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1">
              Sort: {sortOptions.find(o => o.value === sortBy)?.label}
              <FiChevronDown size={16} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            {sortOptions.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onClick={() => onSortChange(option.value)}
                className="flex items-center justify-between cursor-pointer"
              >
                {option.label}
                {sortBy === option.value && <FiCheck size={16} className="text-primary-600" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* View Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1">
              View: {viewOptions.find(o => o.value === viewMode)?.label}
              <FiChevronDown size={16} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            {viewOptions.map((option) => {
              const Icon = option.icon;
              return (
                <DropdownMenuItem
                  key={option.value}
                  onClick={() => onViewChange(option.value)}
                  className="flex items-center justify-between cursor-pointer"
                >
                  <span className="flex items-center gap-2">
                    <Icon size={16} />
                    {option.label}
                  </span>
                  {viewMode === option.value && <FiCheck size={16} className="text-primary-600" />}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
