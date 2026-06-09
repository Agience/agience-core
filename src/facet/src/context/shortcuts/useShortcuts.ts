import { useContext } from 'react';
import { ShortcutsContext } from './ShortcutContext';
import type { ShortcutsContextValue } from './types';

export function useShortcuts(): ShortcutsContextValue {
  const context = useContext(ShortcutsContext);
  if (!context) {
    throw new Error('useShortcuts must be used within a ShortcutsProvider');
  }
  return context;
}
