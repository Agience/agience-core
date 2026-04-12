// frontend/src/api/secrets.ts
import api from './api';

/**
 * Generic Secrets API
 *
 * Manages encrypted credentials: LLM keys, GitHub tokens, integration keys, etc.
 */

export interface SecretResponse {
  id: string;
  type: string;
  provider: string;
  label: string;
  created_time: string;
  is_default: boolean;
}

export interface SecretCreateRequest {
  type: string;
  provider: string;
  label: string;
  value: string;
  is_default?: boolean;
}

/**
 * List stored secrets, optionally filtered by type and/or provider.
 */
export async function listSecrets(
  type?: string,
  provider?: string
): Promise<SecretResponse[]> {
  const params: Record<string, string> = {};
  if (type) params.type = type;
  if (provider) params.provider = provider;
  const response = await api.get<SecretResponse[]>('/secrets', { params });
  return response.data;
}

/**
 * Store a new secret (value encrypted on server). Returns all secrets.
 */
export async function addSecret(
  request: SecretCreateRequest
): Promise<SecretResponse[]> {
  const response = await api.post<SecretResponse[]>('/secrets', request);
  return response.data;
}

/**
 * Delete a stored secret. Returns remaining secrets.
 */
export async function deleteSecret(secretId: string): Promise<SecretResponse[]> {
  const response = await api.delete<SecretResponse[]>(`/secrets/${secretId}`);
  return response.data;
}

/**
 * Mark a secret as the default for its (type, provider) combination.
 */
export async function setDefaultSecret(
  secretId: string
): Promise<SecretResponse[]> {
  const response = await api.post<SecretResponse[]>(
    `/secrets/${secretId}/set-default`
  );
  return response.data;
}
