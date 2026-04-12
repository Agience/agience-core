// frontend/src/components/browser/SearchBar.tsx
import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  placeholder?: string;
  recentSearches?: string[];
  resultCount?: number;
  totalCount?: number;
}

export default function SearchBar({
  value,
  onChange,
  onClear,
  placeholder = 'Search cards...',
  recentSearches = [],
  resultCount,
  totalCount,
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [showRecent, setShowRecent] = useState(false);
  
  // Focus search on "/" key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Focus search on "/" or Ctrl+F
      if ((e.key === '/' && !e.ctrlKey && !e.metaKey) || (e.key === 'f' && (e.ctrlKey || e.metaKey))) {
        // Don't trigger if already in an input
        if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') {
          return;
        }
        e.preventDefault();
        inputRef.current?.focus();
      }
      
      // Clear search on Escape
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        onClear();
        inputRef.current?.blur();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClear]);
  
  const handleFocus = () => {
    if (recentSearches.length > 0 && !value) {
      setShowRecent(true);
    }
  };
  
  const handleBlur = () => {
    // Delay to allow clicking on recent searches
    setTimeout(() => setShowRecent(false), 200);
  };
  
  const handleRecentClick = (search: string) => {
    onChange(search);
    setShowRecent(false);
    inputRef.current?.focus();
  };
  
  const hasValue = value.trim().length > 0;
  const showCount = resultCount !== undefined && totalCount !== undefined;
  
  return (
    <div className="relative flex-1 max-w-md">
      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder={placeholder}
          className="w-full pl-10 pr-20 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
        
        {/* Count Badge */}
        {showCount && (
          <div className="absolute right-10 top-1/2 -translate-y-1/2 px-2 py-0.5 text-xs font-medium text-gray-600 bg-gray-100 rounded">
            {hasValue ? (
              <span>
                {resultCount} / {totalCount}
              </span>
            ) : (
              <span>{totalCount}</span>
            )}
          </div>
        )}
        
        {/* Clear Button */}
        {hasValue && (
          <button
            onClick={onClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 rounded transition-colors"
            title="Clear search (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      
      {/* Recent Searches Dropdown */}
      {showRecent && recentSearches.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-10">
          <div className="px-3 py-2 text-xs font-medium text-gray-500 border-b border-gray-100">
            Recent Searches
          </div>
          <div className="py-1">
            {recentSearches.map((search, index) => (
              <button
                key={index}
                onClick={() => handleRecentClick(search)}
                className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {search}
              </button>
            ))}
          </div>
        </div>
      )}
      
      {/* Keyboard Hint */}
      {!hasValue && (
        <div className="absolute left-3 top-full mt-1 text-xs text-gray-400">
          Press <kbd className="px-1 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs">/ or Ctrl+F</kbd> to search
        </div>
      )}
    </div>
  );
}
