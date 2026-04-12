import { useContext } from 'react';
import { ConfirmContext } from './ConfirmContext';
import type { ConfirmContextValue } from './types';

export function useConfirm(): ConfirmContextValue {
  const context = useContext(ConfirmContext);
  if (!context) {
    throw new Error('useConfirm must be used within a DialogProvider');
  }
  return context;
}
