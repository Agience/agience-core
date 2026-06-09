import { createContext } from 'react';
import type { ConfirmContextValue } from './types';

export const ConfirmContext = createContext<ConfirmContextValue | undefined>(undefined);
