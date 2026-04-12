// src/api/types/collection.ts

// Body you POST to /collections and /collections/{id}/shares
export interface CollectionCreate {
  name: string;
  description?: string;
}

// Body you PATCH to /collections/{id}
export interface CollectionUpdate {
  name?: string;
  description?: string;
}

// What your GET /collections returns
export interface CollectionResponse {
  id: string;
  name: string;
  description: string;
  created_by: string;
  created_time: string;   // ISO datetime
  modified_time: string;  // ISO datetime
}

export interface CollectionCommitResponse {
  id: string;
  message: string;
  author_id: string;
  subject_user_id?: string | null;
  presenter_type?: string | null;
  presenter_id?: string | null;
  client_id?: string | null;
  host_id?: string | null;
  server_id?: string | null;
  agent_id?: string | null;
  api_key_id?: string | null;
  confirmation?: string | null;
  changeset_type?: string | null;
  timestamp: string;
  item_ids: string[];
}


