import { createContext } from 'react';
import type { ShortcutsContextValue } from './types';

export const ShortcutsContext = createContext<ShortcutsContextValue | undefined>(undefined);
