// frontend/src/utils/search.ts
// Search utilities for workspace artifact filtering

import { Artifact } from '../context/workspace/workspace.types';

/**
 * Simple fuzzy matching - checks if search term appears in text (case-insensitive)
 * with some tolerance for character proximity
 */
export function fuzzyMatch(text: string, search: string): boolean {
  if (!search) return true;
  if (!text) return false;
  
  const lowerText = text.toLowerCase();
  const lowerSearch = search.toLowerCase();
  
  // Exact substring match
  if (lowerText.includes(lowerSearch)) return true;
  
  // Simple fuzzy: all chars in search appear in order in text
  let searchIndex = 0;
  for (let i = 0; i < lowerText.length && searchIndex < lowerSearch.length; i++) {
    if (lowerText[i] === lowerSearch[searchIndex]) {
      searchIndex++;
    }
  }
  return searchIndex === lowerSearch.length;
}

/**
 * Extract searchable text from an artifact
 */
export function getArtifactSearchText(artifact: Artifact): string {
  const parts: string[] = [];
  
  // Parse context to get title, filename, description
  try {
    const context = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
    if (context?.title) parts.push(context.title);
    if (context?.filename) parts.push(context.filename);
    if (context?.description) parts.push(context.description);
    if (context?.tags && Array.isArray(context.tags)) {
      parts.push(...context.tags);
    }
  } catch {
    // If context parsing fails, just use raw context
    if (artifact.context) parts.push(String(artifact.context));
  }
  
  // Add content if available
  if (artifact.content) parts.push(artifact.content);
  
  return parts.join(' ').toLowerCase();
}

/**
 * Extract MIME type category from full MIME type
 * e.g., "image/png" -> "image", "application/pdf" -> "pdf"
 */
export function getContentTypeCategory(contentType?: string): string {
  if (!contentType) return 'unknown';

  // Special cases
  if (contentType === 'application/pdf') return 'pdf';
  if (contentType.startsWith('application/vnd.openxmlformats') || contentType.startsWith('application/vnd.ms-')) {
    return 'document';
  }

  // General categories
  const category = contentType.split('/')[0];
  return category || 'unknown';
}

/**
 * Parse search query to extract filters and text
 * Supports:
 * - Plain text: "api design"
 * - Tags: "#python #api"
 * - State filters: "is:new", "is:modified", "is:archived"
 * - Type filters: "type:pdf", "type:image"
 */
export interface SearchFilters {
  text: string;
  tags: string[];
  states: Array<'draft' | 'committed' | 'archived'>;
  mimeCategories: string[];
}

export function parseSearchQuery(query: string): SearchFilters {
  const filters: SearchFilters = {
    text: '',
    tags: [],
    states: [],
    mimeCategories: [],
  };
  
  if (!query) return filters;
  
  const words = query.split(/\s+/);
  const textParts: string[] = [];
  
  for (const word of words) {
    if (!word) continue;
    
    // Tag filter: #python
    if (word.startsWith('#')) {
      filters.tags.push(word.slice(1).toLowerCase());
      continue;
    }
    
    // State filter: is:new
    if (word.startsWith('is:')) {
      const state = word.slice(3).toLowerCase();
      if (state === 'draft' || state === 'committed' || state === 'archived') {
        filters.states.push(state);
      }
      continue;
    }
    
    // Type filter: type:pdf
    if (word.startsWith('type:')) {
      const type = word.slice(5).toLowerCase();
      filters.mimeCategories.push(type);
      continue;
    }
    
    // Regular text
    textParts.push(word);
  }
  
  filters.text = textParts.join(' ');
  return filters;
}

/**
 * Filter artifacts based on search query
 */
export function filterArtifacts(artifacts: Artifact[], query: string): Artifact[] {
  if (!query.trim()) return artifacts;
  
  const filters = parseSearchQuery(query);
  
  return artifacts.filter(artifact => {
    // Text search (title, description, content, tags)
    if (filters.text) {
      const searchText = getArtifactSearchText(artifact);
      if (!fuzzyMatch(searchText, filters.text)) {
        return false;
      }
    }
    
    // Tag filter
    if (filters.tags.length > 0) {
      try {
        const context = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
        const artifactTags = (context?.tags || []).map((t: string) => t.toLowerCase());
        
        // All specified tags must be present
        for (const tag of filters.tags) {
          if (!artifactTags.includes(tag)) {
            return false;
          }
        }
      } catch {
        // If context parsing fails, artifact doesn't match tag filter
        return false;
      }
    }
    
    // State filter
    if (filters.states.length > 0) {
      const artifactState = artifact.state as 'draft' | 'committed' | 'archived';
      if (!filters.states.includes(artifactState)) {
        return false;
      }
    }
    
    // MIME category filter
    if (filters.mimeCategories.length > 0) {
      try {
        const context = typeof artifact.context === 'string' ? JSON.parse(artifact.context) : artifact.context;
        const artifactContentType = context?.content_type || '';
        const artifactCategory = getContentTypeCategory(artifactContentType);
        
        if (!filters.mimeCategories.includes(artifactCategory)) {
          return false;
        }
      } catch {
        return false;
      }
    }
    
    return true;
  });
}

/**
 * Highlight matching text in a string
 * Returns array of { text: string, highlight: boolean } objects
 */
export function highlightMatches(text: string, search: string): Array<{ text: string; highlight: boolean }> {
  if (!search || !text) return [{ text, highlight: false }];
  
  const lowerText = text.toLowerCase();
  const lowerSearch = search.toLowerCase();
  
  const parts: Array<{ text: string; highlight: boolean }> = [];
  let lastIndex = 0;
  let index = lowerText.indexOf(lowerSearch);
  
  while (index !== -1) {
    // Add non-matching text before match
    if (index > lastIndex) {
      parts.push({ text: text.slice(lastIndex, index), highlight: false });
    }
    
    // Add matching text
    parts.push({ text: text.slice(index, index + search.length), highlight: true });
    
    lastIndex = index + search.length;
    index = lowerText.indexOf(lowerSearch, lastIndex);
  }
  
  // Add remaining text
  if (lastIndex < text.length) {
    parts.push({ text: text.slice(lastIndex), highlight: false });
  }
  
  return parts;
}
