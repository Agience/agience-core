// frontend/src/hooks/useWorkspaceSearch.ts
// Hook for workspace artifact search and filtering

import { useState, useMemo, useCallback } from 'react';
import { Artifact } from '../context/workspace/workspace.types';
import { filterArtifacts, parseSearchQuery, SearchFilters } from '../utils/search';

const MAX_RECENT_SEARCHES = 5;

export function useWorkspaceSearch(artifacts: Artifact[], externalQuery?: string) {
  const [internalQuery, setInternalQuery] = useState('');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  
  // Use external query if provided, otherwise use internal state
  const searchQuery = externalQuery !== undefined ? externalQuery : internalQuery;
  
  // Parse the search query into filters
  const filters: SearchFilters = useMemo(() => {
    return parseSearchQuery(searchQuery);
  }, [searchQuery]);
  
  // Apply search filters to artifacts
  const filteredArtifacts = useMemo(() => {
    return filterArtifacts(artifacts, searchQuery);
  }, [artifacts, searchQuery]);
  
  // Update search query (only used when externalQuery is not provided)
  const updateSearch = useCallback((query: string) => {
    if (externalQuery !== undefined) return; // Ignore if external query is controlling
    
    setInternalQuery(query);
    
    // Add to recent searches if it's a non-empty, new search
    if (query.trim() && !recentSearches.includes(query.trim())) {
      setRecentSearches(prev => {
        const updated = [query.trim(), ...prev];
        return updated.slice(0, MAX_RECENT_SEARCHES);
      });
    }
  }, [recentSearches, externalQuery]);
  
  // Clear search
  const clearSearch = useCallback(() => {
    if (externalQuery !== undefined) return; // Ignore if external query is controlling
    setInternalQuery('');
  }, [externalQuery]);
  
  // Check if search is active
  const isSearchActive = searchQuery.trim().length > 0;
  
  // Get result count
  const resultCount = isSearchActive ? filteredArtifacts.length : artifacts.length;
  
  return {
    searchQuery,
    filters,
    filteredArtifacts,
    recentSearches,
    updateSearch,
    clearSearch,
    isSearchActive,
    resultCount,
    totalCount: artifacts.length,
  };
}
