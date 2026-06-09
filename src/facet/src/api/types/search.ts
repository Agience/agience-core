// api/types/search.ts

export interface SearchRequest {
  query_text: string;
  collection_id?: string;
  filters?: Record<string, unknown>;
  from_?: number;
  size?: number;
  use_vector?: boolean;
  use_bm25?: boolean;
  sort?: 'relevance' | 'recency';
  highlight?: boolean;
  aperture?: number;  // Relevance width: 0.0 (narrow, precision only) to 1.0 (wide, show all). Higher = more results. Default 0.5
}

export interface SearchHitPresence {
  in_current_workspace: boolean;
  in_other_workspace: boolean;
  collections: string[];
}

export interface SearchHit {
  id: string;  // Document ID in search index
  score: number;
  root_id: string;  // Artifact root ID
  version_id: string;  // Version/artifact ID (for workspace artifacts, this is the artifact ID)
  collection_id?: string;  // Collection this artifact belongs to
}

export interface SearchFacetBucket {
  key: string;
  doc_count: number;
}

export interface SearchFacet {
  field: string;
  buckets: SearchFacetBucket[];
}

export interface SearchResponse {
  hits: SearchHit[];
  total: number;
  query_text: string;
  parsed_query?: string;
  corrections?: string[];
  used_hybrid: boolean;
  from: number;
  size: number;
}

export interface SuggestionsRequest {
  query_text: string;
  collection_id?: string;
  limit?: number;
  types?: ('tags' | 'titles')[];
}

export interface TagSuggestion {
  value: string;
  count: number;
}

export interface TitleSuggestion {
  id: string;
  title: string;
}

export interface SuggestionsResponse {
  tags?: TagSuggestion[];
  titles?: TitleSuggestion[];
}

