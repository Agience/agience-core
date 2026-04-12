// api/search.ts
import api from './api';
import type {
  SearchRequest,
  SearchResponse,
  SuggestionsRequest,
  SuggestionsResponse,
  SearchHit,
} from './types/search';

type UnifiedSearchRequest = {
  query_text: string;
  scope?: string[];
  use_hybrid?: boolean;
  aperture?: number;
  from?: number;
  size?: number;
  sort?: 'relevance' | 'recency';
  highlight?: boolean;
};

type UnifiedHit = {
  id: string;
  score: number;
  root_id: string;
  version_id: string;
  collection_id?: string;
};

type UnifiedSearchResponse = {
  hits: UnifiedHit[];
  total: number;
  query_text: string;
  parsed_query?: string;
  corrections?: string[];
  used_hybrid: boolean;
  from: number;
  size: number;
};

/**
 * Search workspace artifacts
 */
export async function searchWorkspace(request: SearchRequest): Promise<SearchResponse> {
  const body: UnifiedSearchRequest = {
    query_text: request.query_text,
    scope: request.collection_id ? [request.collection_id] : undefined,
    use_hybrid: undefined, // let backend auto-decide
    aperture: request.aperture,
    from: request.from_ ?? 0,
    size: request.size ?? 20,
    sort: request.sort ?? 'relevance',
    highlight: request.highlight ?? true,
  };
  const resp = await api.post<UnifiedSearchResponse>('/artifacts/search', body);
  return mapUnifiedResponse(resp.data);
}

/**
 * Search collection artifacts
 */
export async function searchCollection(request: SearchRequest): Promise<SearchResponse> {
  const body: UnifiedSearchRequest = {
    query_text: request.query_text,
    scope: request.collection_id ? [request.collection_id] : undefined,
    use_hybrid: undefined,
    aperture: request.aperture,
    from: request.from_ ?? 0,
    size: request.size ?? 20,
    sort: request.sort ?? 'relevance',
    highlight: request.highlight ?? true,
  };
  const resp = await api.post<UnifiedSearchResponse>('/artifacts/search', body);
  return mapUnifiedResponse(resp.data);
}

/**
 * Global search across all workspaces and collections
 */
export async function searchGlobal(
  request: SearchRequest,
): Promise<SearchResponse> {
  const body: UnifiedSearchRequest = {
    query_text: request.query_text,
    // No IDs - search all accessible artifacts
    use_hybrid: undefined, // let backend auto-decide
    aperture: request.aperture,
    from: request.from_ ?? 0,
    size: request.size ?? 20,
    sort: request.sort ?? 'relevance',
    highlight: request.highlight ?? true,
  };
  const resp = await api.post<UnifiedSearchResponse>('/artifacts/search', body);
  return mapUnifiedResponse(resp.data);
}

/**
 * Get autocomplete suggestions for workspace search
 */
export async function getWorkspaceSuggestions(request: SuggestionsRequest): Promise<SuggestionsResponse> {
  // Suggestions are not supported in v3.1 yet; return empty to avoid 404s
  void request; // mark used
  return { tags: [], titles: [] };
}

/**
 * Get autocomplete suggestions for collection search
 */
export async function getCollectionSuggestions(request: SuggestionsRequest): Promise<SuggestionsResponse> {
  // Suggestions are not supported in v3.1 yet; return empty to avoid 404s
  void request; // mark used
  return { tags: [], titles: [] };
}

// Map backend unified response to frontend SearchResponse shape
function mapUnifiedResponse(data: UnifiedSearchResponse): SearchResponse {
  const hits: SearchHit[] = (data?.hits || []).map((h: UnifiedHit) => ({
    id: h.id,
    score: h.score,
    root_id: h.root_id,
    version_id: h.version_id,
    collection_id: h.collection_id,
  }));

  return {
    hits,
    total: data?.total ?? hits.length,
    query_text: data?.query_text ?? '',
    parsed_query: data?.parsed_query,
    corrections: data?.corrections ?? [],
    used_hybrid: data?.used_hybrid ?? false,
    from: data?.from ?? 0,
    size: data?.size ?? 20,
  };
}

