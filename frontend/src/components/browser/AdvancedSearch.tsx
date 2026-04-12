// components/browser/AdvancedSearch.tsx
import { useState, useRef, useEffect, useCallback } from 'react';
import { Search, X, Loader, SlidersHorizontal } from 'lucide-react';
import { 
  searchWorkspace, 
  searchCollection,
  searchGlobal,
  getWorkspaceSuggestions, 
  getCollectionSuggestions 
} from '../../api/search';
import type {
  SearchRequest,
  SearchResponse,
  SuggestionsRequest,
  SuggestionsResponse,
  TagSuggestion,
  TitleSuggestion,
} from '../../api/types/search';
import ApertureControl from '../search/ApertureControl';
import { useShortcuts } from '@/context/shortcuts/useShortcuts';

interface AdvancedSearchProps {
  /** 'workspace', 'collection', or 'global' (searches both) */
  scope: 'workspace' | 'collection' | 'global';
  /** ID of workspace or collection to search (empty for global) */
  scopeId: string;
  /** Optional placeholder */
  placeholder?: string;
  /** Callback when search results change */
  onResults?: (results: SearchResponse) => void;
  /** Callback when search is cleared */
  onClear?: () => void;
  /** Enable/disable autocomplete suggestions */
  enableSuggestions?: boolean;
  /** Controlled aperture value (from header quick controls) */
  aperture?: number;
  /** Callback when aperture changes */
  onApertureChange?: (value: number) => void;
  /** Controlled sort mode (from header quick controls) */
  sortMode?: 'relevance' | 'recency';
  /** Trigger to clear the search input (increment to clear) */
  clearTrigger?: number;
  /** Compact mode for sidebar use - reduces padding and hides result count */
  compact?: boolean;
  /** For global scope, choose which sources to include. */
  globalSourceScope?: 'all' | 'collections' | 'workspaces';
}

export default function AdvancedSearch({
  scope,
  scopeId,
  placeholder = 'Search cards...',
  onResults,
  onClear,
  enableSuggestions = true,
  aperture: controlledAperture,
  onApertureChange,
  sortMode: controlledSortMode,
  clearTrigger,
  compact = false,
  globalSourceScope = 'all',
}: AdvancedSearchProps) {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionsResponse>({});
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [customFilters, setCustomFilters] = useState<Array<{field:string,op:string,value:string}>>([]);
  const [addingCustom, setAddingCustom] = useState(false);
  const [newCustomField, setNewCustomField] = useState('');
  const [newCustomValue, setNewCustomValue] = useState('');
  const { registerShortcut } = useShortcuts();
  
  // Use controlled values if provided, otherwise use defaults
  // Aperture: 0.0 = show all results, 1.0 = only perfect matches
  const aperture = controlledAperture ?? 0.5;

  const sortMode = controlledSortMode ?? 'relevance';

  const handleApertureChange = (value: number) => {
    if (onApertureChange) {
      onApertureChange(value);
    }
    // otherwise ignore - no internal UI to change aperture here
  };

  const addCustomFilter = () => {
    if (!newCustomField.trim()) return;
    setCustomFilters((s) => [...s, { field: newCustomField.trim(), op: 'is', value: newCustomValue }]);
    setNewCustomField('');
    setNewCustomValue('');
    setAddingCustom(false);
  };
  
  const inputRef = useRef<HTMLInputElement>(null);
  const searchDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const suggestDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Execute search
  const executeSearch = useCallback(async (
    searchQuery: string
  ) => {
    if (!searchQuery.trim()) {
      setResults(null);
      if (onResults) onResults({ hits: [], total: 0, query_text: '', used_hybrid: false, from: 0, size: 20 });
      if (onClear) onClear();
      return;
    }
    
    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    
    setIsSearching(true);
    
    try {
      const request: SearchRequest = {
        query_text: searchQuery,
        from_: 0,
        size: 100, // Load more results for Browser display
        sort: sortMode,
        aperture: aperture, // Relevance width control
      };
      
      if (scope === 'global') {
        // Global search: searches all accessible artifacts
        const response = await searchGlobal(request);
        setResults(response);
        if (onResults) onResults(response);
      } else {
        // Scoped search
        request.collection_id = scopeId;
        
        const response = scope === 'workspace'
          ? await searchWorkspace(request)
          : await searchCollection(request);
        
        setResults(response);
        if (onResults) onResults(response);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // Silently ignore cancelled requests
      }
      console.error('Search failed:', error);
      setResults({ hits: [], total: 0, query_text: '', used_hybrid: false, from: 0, size: 0 });
    } finally {
      setIsSearching(false);
    }
  }, [scope, scopeId, sortMode, aperture, onResults, onClear]);
  
  // Fetch suggestions
  const fetchSuggestions = useCallback(async (suggestQuery: string) => {
    if (!suggestQuery.trim() || !enableSuggestions) {
      setSuggestions({});
      return;
    }
    
    try {
      const request: SuggestionsRequest = {
        query_text: suggestQuery,
        limit: 8,
        types: ['tags', 'titles'],
      };
      
      if (scope !== 'global') {
        request.collection_id = scopeId;
      }
      
      const response = scope === 'workspace'
        ? await getWorkspaceSuggestions(request)
        : await getCollectionSuggestions(request);
      
      setSuggestions(response);
      setShowSuggestions(true);
    } catch (error) {
      console.error('Suggestions failed:', error);
      setSuggestions({});
    }
  }, [scope, scopeId, enableSuggestions]);
  
  // Handle query change with debouncing
  const handleQueryChange = (value: string) => {
    setQuery(value);
    
    // Clear previous timers
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (suggestDebounceRef.current) clearTimeout(suggestDebounceRef.current);
    
    // Debounce search (300ms)
    searchDebounceRef.current = setTimeout(() => {
      executeSearch(value);
    }, 300);
    
    // Debounce suggestions (200ms - faster for autocomplete feel)
    suggestDebounceRef.current = setTimeout(() => {
      fetchSuggestions(value);
    }, 200);
  };
  
  // Clear search
  const handleClear = useCallback(() => {
    setQuery('');
    setResults(null);
    setShowSuggestions(false);
    setSuggestions({});
    if (onResults) onResults({ hits: [], total: 0, query_text: '', used_hybrid: false, from: 0, size: 0 });
    if (onClear) onClear();
  }, [onResults, onClear]);

  // Handle external clear trigger (when source changes)
  useEffect(() => {
    if (clearTrigger !== undefined && clearTrigger > 0) {
      setQuery('');
      setResults(null);
      setSuggestions({});
      setShowSuggestions(false);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  }, [clearTrigger]);
  
  // Load more results (infinite scroll) - Now handled by Browser component pagination
  
  // Handle suggestion click
  const handleSuggestionClick = (value: string) => {
    setQuery(value);
    setShowSuggestions(false);
    executeSearch(value);
    inputRef.current?.focus();
  };
  
  // Results are now displayed in Browser component, not in dropdown
  
  // Keyboard shortcuts
  useEffect(() => {
    const unregister = registerShortcut({
      id: 'search:focus-global',
      label: 'Focus global search',
      group: 'Navigation',
      groupTitle: 'Navigation',
      groupOrder: 1,
      combos: ['/'],
      handler: (event) => {
        const target = event.target as HTMLElement | null;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
          return;
        }
        event.preventDefault();
        inputRef.current?.focus();
      },
      options: {
        description: 'Jump to the global search field',
      },
    });

    return unregister;
  }, [registerShortcut]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        if (query) {
          handleClear();
        } else {
          inputRef.current?.blur();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [query, handleClear]);
  
  // Re-search when sort or aperture changes
  useEffect(() => {
    if (query.trim()) {
      executeSearch(query);
    }
    // Only re-run when sortMode or aperture change (not query or executeSearch to avoid loops)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortMode, aperture, globalSourceScope]);
  
  const hasSuggestions = (suggestions.tags?.length ?? 0) > 0 || (suggestions.titles?.length ?? 0) > 0;
  
  return (
    <div className="relative w-full max-w-none">
      <div className="flex flex-col gap-2">
        {/* Search Input */}
        <div className="relative">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 ${compact ? 'h-5 w-5' : 'h-5 w-5'}`} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onFocus={() => {
              if (hasSuggestions) setShowSuggestions(true);
            }}
            placeholder={placeholder}
            className={`w-full ${compact ? 'pl-11 pr-16 py-2.5' : 'pl-11 pr-28 py-2.5'} text-sm border border-border rounded-lg bg-white/95 shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
          />
          
          {/* Right side: controls + clear */}
          <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex items-center ${compact ? 'gap-1' : 'gap-1'}`}>
            {/* Result count - hidden in compact mode */}
            {results && !compact && (
              <span className="text-xs text-gray-500 px-2">
                {results.hits.length} {results.hits.length === 1 ? 'result' : 'results'}
              </span>
            )}
            
            {/* Loading spinner - hidden in compact mode */}
            {isSearching && !compact && (
              <Loader className="h-4 w-4 text-purple-500 animate-spin" />
            )}
            
            {/* Clear button (only when there's a query) - moved before filters so it's immediately accessible */}
            {query && (
              <button
                onClick={handleClear}
                className="p-1 hover:bg-gray-100 rounded transition-colors"
                title="Clear (Esc)"
              >
                <X className="h-4 w-4 text-gray-500" />
              </button>
            )}

            {/* Advanced filters toggle - always visible so users can open filters before typing */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={`p-1 rounded transition-colors ${
                showAdvanced ? 'bg-purple-100 text-purple-600' : 'hover:bg-gray-100 text-gray-500'
              }`}
              title="Advanced search filters"
            >
              <SlidersHorizontal className="h-4 w-4" />
            </button>
          </div>
        </div>
        
        {/* Advanced Search Panel - Drops down from search bar */}
        {showAdvanced && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-xl z-50 p-5">
            <div className="grid grid-cols-2 gap-6">
              {/* Left Column */}
              <div className="space-y-4">
                {/* Tags Filter */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-2 block">Has tag</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Enter tag..."
                      className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <select className="w-28 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500">
                      <option value="is">is like</option>
                      <option value="exact">exact</option>
                    </select>
                  </div>
                </div>
                
                {/* State Filter */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-2 block">State</label>
                  <select className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500">
                    <option value="">All states</option>
                    <option value="draft">Draft</option>
                    <option value="committed">Committed</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
                
                {/* MIME Type Filter */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-2 block">Type</label>
                  <select className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-purple-500">
                    <option value="">All types</option>
                    <option value="text">Text</option>
                    <option value="image">Image</option>
                    <option value="video">Video</option>
                    <option value="audio">Audio</option>
                    <option value="pdf">PDF</option>
                    <option value="office">Office</option>
                  </select>
                </div>

                {/* Custom / Metadata Filters */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-2 block">Custom filters</label>
                  {customFilters.length === 0 ? (
                    <div className="text-xs text-gray-500 mb-2">Add filters for metadata (e.g., color: red) after you've found results.</div>
                  ) : (
                    <ul className="space-y-1 mb-2">
                      {customFilters.map((f, idx) => (
                        <li key={idx} className="text-sm text-gray-700">{f.field} {f.op} {f.value}</li>
                      ))}
                    </ul>
                  )}
                  {addingCustom ? (
                    <div className="flex gap-2">
                      <input value={newCustomField} onChange={(e) => setNewCustomField(e.target.value)} placeholder="field" className="px-2 py-1 border rounded w-28" />
                      <select value={'is'} className="px-2 py-1 border rounded">
                        <option value="is">is</option>
                        <option value="like">is like</option>
                      </select>
                      <input value={newCustomValue} onChange={(e) => setNewCustomValue(e.target.value)} placeholder="value" className="px-2 py-1 border rounded flex-1" />
                      <button onClick={addCustomFilter} className="px-2 bg-purple-600 text-white rounded">Add</button>
                    </div>
                  ) : (
                    <button onClick={() => setAddingCustom(true)} className="text-xs text-purple-600">+ Add metadata filter</button>
                  )}
                </div>
              </div>
              
              {/* Right Column */}
              <div className="space-y-4">
                {/* Result breadth (aperture) */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-1 block">How broad should results be?</label>
                  <p className="text-xs text-gray-500 mb-2">Precise finds only very close matches. Wide includes related ideas.</p>
                  <ApertureControl 
                    value={aperture}
                    onChange={handleApertureChange}
                    show={true}
                  />
                </div>

                {/* Match style (user-friendly) */}
                <div>
                  <label className="text-xs font-medium text-gray-700 mb-2 block">How should we match results?</label>
                  <div className="space-y-2">
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input type="radio" name="searchType" value="smart" defaultChecked className="text-purple-600 mt-1" />
                      <div>
                        <div className="text-sm">Smart (recommended)</div>
                        <div className="text-xs text-gray-500">Finds matches by meaning and the words you typed.</div>
                      </div>
                    </label>
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input type="radio" name="searchType" value="meaning" className="text-purple-600 mt-1" />
                      <div>
                        <div className="text-sm">Idea match</div>
                        <div className="text-xs text-gray-500">Looks for results that match the idea, even if different words are used.</div>
                      </div>
                    </label>
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input type="radio" name="searchType" value="exact" className="text-purple-600 mt-1" />
                      <div>
                        <div className="text-sm">Exact words</div>
                        <div className="text-xs text-gray-500">Only shows results that contain the exact words you typed.</div>
                      </div>
                    </label>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Bottom Actions */}
            <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
              <button
                onClick={() => {
                  setShowAdvanced(false);
                  // Reset filters
                }}
                className="text-sm text-gray-600 hover:text-gray-700"
              >
                Clear filters
              </button>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowAdvanced(false)}
                  className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowAdvanced(false);
                    executeSearch(query);
                  }}
                  className="px-4 py-2 text-sm text-white bg-purple-600 rounded hover:bg-purple-700"
                >
                  Apply filters
                </button>
              </div>
            </div>
          </div>
        )}
        
        {/* Simple controls removed: highlighting and inline sort were confusing. Use Advanced filters instead. */}
      </div>
      
      {/* Suggestions Dropdown */}
      {showSuggestions && hasSuggestions && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-64 overflow-auto">
          {/* Tags */}
          {suggestions.tags && suggestions.tags.length > 0 && (
            <div className="py-2">
              <div className="px-3 py-1 text-xs font-medium text-gray-500 uppercase">
                Tags
              </div>
              {suggestions.tags.map((tag: TagSuggestion) => (
                <button
                  key={tag.value}
                  onClick={() => handleSuggestionClick(`tag:=${tag.value}`)}
                  className="w-full px-3 py-1.5 text-sm text-left hover:bg-gray-50 flex items-center justify-between group"
                >
                  <span className="text-gray-700">{tag.value}</span>
                  <span className="text-xs text-gray-400 group-hover:text-gray-500">
                    {tag.count}
                  </span>
                </button>
              ))}
            </div>
          )}
          
          {/* Titles */}
          {suggestions.titles && suggestions.titles.length > 0 && (
            <div className="py-2 border-t border-gray-100">
              <div className="px-3 py-1 text-xs font-medium text-gray-500 uppercase">
                Titles
              </div>
              {suggestions.titles.map((title: TitleSuggestion) => (
                <button
                  key={title.id}
                  onClick={() => handleSuggestionClick(title.title)}
                  className="w-full px-3 py-1.5 text-sm text-left hover:bg-gray-50 text-gray-700 truncate"
                >
                  {title.title}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Results are displayed in the Browser component's artifact grid */}
    </div>
  );
}
