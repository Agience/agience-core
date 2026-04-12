// context/preferences/PreferencesProvider.tsx
import { useState, useEffect, useCallback } from 'react';
import { PreferencesContext } from './PreferencesContext';
import { Preferences, PreferencesProviderProps } from './preferences.types';
import { getPreferences, updatePreferences as apiUpdatePreferences } from '../../api/preferences';
import { useAuth } from '../../hooks/useAuth';

export function PreferencesProvider({ children }: PreferencesProviderProps) {
  const { isAuthenticated } = useAuth();
  const [preferences, setPreferences] = useState<Preferences>({});
  const [isLoading, setIsLoading] = useState(true);

  // Load preferences on mount (only if authenticated)
  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }

    const loadPreferences = async () => {
      try {
        const prefs = await getPreferences();
        setPreferences(prefs);
      } catch (error) {
        console.error('Failed to load preferences:', error);
        // Start with empty preferences on error
        setPreferences({});
      } finally {
        setIsLoading(false);
      }
    };

    loadPreferences();
  }, [isAuthenticated]);

  // Update preferences (merges and saves to backend)
  const updatePreferences = useCallback(async (newPrefs: Partial<Preferences>) => {
    try {
      // Optimistically update local state
      setPreferences(prev => {
        const merged = { ...prev };
        Object.keys(newPrefs).forEach(key => {
          if (typeof newPrefs[key] === 'object' && !Array.isArray(newPrefs[key])) {
            // Deep merge for nested objects
            merged[key] = { ...(prev[key] as object || {}), ...(newPrefs[key] as object) };
          } else {
            merged[key] = newPrefs[key];
          }
        });
        return merged;
      });

      // Save to backend
      const updated = await apiUpdatePreferences(newPrefs);
      setPreferences(updated);
    } catch (error) {
      console.error('Failed to update preferences:', error);
      // Reload preferences on error to ensure consistency
      try {
        const prefs = await getPreferences();
        setPreferences(prefs);
      } catch (reloadError) {
        console.error('Failed to reload preferences:', reloadError);
      }
    }
  }, []);

  return (
    <PreferencesContext.Provider value={{ preferences, updatePreferences, isLoading }}>
      {children}
    </PreferencesContext.Provider>
  );
}
