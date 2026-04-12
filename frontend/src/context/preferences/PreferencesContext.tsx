// context/preferences/PreferencesContext.tsx
import { createContext } from 'react';
import { PreferencesContextType } from './preferences.types';

export const PreferencesContext = createContext<PreferencesContextType | undefined>(undefined);
