// frontend/src/api/platform.ts
//
// Platform admin API — successor to the retired `api/admin.ts` module
// and the operator-settings section of `api/setup.ts` (merged 2026-04-06
// when the backend operator_router + admin_router were unified into
// platform_router).
//
// All endpoints under /platform/* require a platform-admin grant
// (write on the authority collection, or the bootstrap fast-path for
// the initial operator from setup). See backend require_platform_admin.

import api from './api';

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export interface PlatformUser {
  id: string;
  email: string;
  name: string;
  picture: string | null;
  is_platform_admin: boolean;
  created_time: string | null;
}

export interface SeedCollection {
  id: string;
  name: string;
  description: string | null;
  artifact_count: number;
}

export async function listUsers(): Promise<PlatformUser[]> {
  const response = await api.get<{ users: PlatformUser[] }>('/platform/users');
  return response.data.users;
}

export async function grantPlatformAdmin(userId: string): Promise<void> {
  await api.post(`/platform/users/${userId}/grant-admin`);
}

export async function revokePlatformAdmin(userId: string): Promise<void> {
  await api.delete(`/platform/users/${userId}/revoke-admin`);
}

export async function listSeedCollections(): Promise<SeedCollection[]> {
  const response = await api.get<SeedCollection[]>('/platform/seed-collections');
  return response.data;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export type PlatformSettings = {
  categories: Record<
    string,
    Array<{ key: string; value: string | null; is_secret: boolean }>
  >;
};

export async function getPlatformSettings(): Promise<PlatformSettings> {
  const response = await api.get<PlatformSettings>('/platform/settings');
  return response.data;
}

export async function getPlatformSettingsByCategory(
  category: string,
): Promise<Array<{ key: string; value: string | null; is_secret: boolean }>> {
  const response = await api.get<
    Array<{ key: string; value: string | null; is_secret: boolean }>
  >(`/platform/settings/${category}`);
  return response.data;
}

export async function updatePlatformSettings(
  settings: Array<{ key: string; value: string; is_secret?: boolean }>,
): Promise<{ updated: number; restart_required: boolean }> {
  const response = await api.patch<{ updated: number; restart_required: boolean }>(
    '/platform/settings',
    { settings },
  );
  return response.data;
}
