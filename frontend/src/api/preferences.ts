// api/preferences.ts
import api from './api';

export interface UserPreferences {
  layout?: {
    sidebarWidth?: number;
    sidebarCollapsed?: boolean;
    browserWidth?: number;
    previewWidth?: number;
    previewCollapsed?: boolean;
  };
  [key: string]: unknown;
}

/**
 * Get user preferences
 */
export async function getPreferences(): Promise<UserPreferences> {
  const response = await api.get<UserPreferences>('/auth/me/preferences');
  return response.data;
}

/**
 * Update user preferences (merges with existing)
 */
export async function updatePreferences(preferences: Partial<UserPreferences>): Promise<UserPreferences> {
  const response = await api.patch<UserPreferences>('/auth/me/preferences', preferences);
  return response.data;
}
