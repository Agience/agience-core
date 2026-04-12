// hooks/usePreferences.ts
import { useContext } from 'react';
import { PreferencesContext } from '../context/preferences/PreferencesContext';

export function usePreferences() {
  const context = useContext(PreferencesContext);
  if (!context) {
    throw new Error('usePreferences must be used within a PreferencesProvider');
  }
  return context;
}
