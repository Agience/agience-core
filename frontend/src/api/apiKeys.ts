import api from './api';

export interface APIKey {
  id: string;
  user_id: string;
  name: string;
  client_id?: string | null;
  host_id?: string | null;
  server_id?: string | null;
  agent_id?: string | null;
  display_label?: string | null;
  scopes: string[];
  resource_filters: Record<string, unknown>;
  created_time: string;
  modified_time?: string | null;
  expires_at?: string | null;
  last_used_at?: string | null;
  is_active: boolean;
}

export interface APIKeyCreateRequest {
  name: string;
  scopes?: string[];
  resource_filters?: Record<string, unknown>;
  expires_at?: string | null;
  client_id?: string;
  host_id?: string;
  server_id?: string;
  agent_id?: string;
  display_label?: string;
}

export interface APIKeyUpdateRequest {
  name?: string;
  scopes?: string[];
  resource_filters?: Record<string, unknown>;
  is_active?: boolean;
  client_id?: string;
  host_id?: string;
  server_id?: string;
  agent_id?: string;
  display_label?: string;
}

export interface APIKeyCreateResponse extends APIKey {
  key: string;
}

export async function createAPIKey(payload: APIKeyCreateRequest): Promise<APIKeyCreateResponse> {
  const response = await api.post<APIKeyCreateResponse>('/api-keys', payload);
  return response.data;
}

export async function listAPIKeys(): Promise<APIKey[]> {
  const response = await api.get<APIKey[]>('/api-keys');
  return response.data;
}

export async function getAPIKey(keyId: string): Promise<APIKey> {
  const response = await api.get<APIKey>(`/api-keys/${keyId}`);
  return response.data;
}

export async function deleteAPIKey(keyId: string): Promise<void> {
  await api.delete(`/api-keys/${keyId}`);
}

export async function updateAPIKey(keyId: string, payload: APIKeyUpdateRequest): Promise<APIKey> {
  const response = await api.patch<APIKey>(`/api-keys/${keyId}`, payload);
  return response.data;
}