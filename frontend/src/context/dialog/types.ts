import type { ReactNode } from 'react';

export type ConfirmTone = 'danger' | 'warn';

export interface ConfirmOptions {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
  icon?: ReactNode;
  confirmIcon?: ReactNode;
  cancelIcon?: ReactNode;
  customContent?: ReactNode;
  secondaryAction?: {
    label: string;
    onAction: () => void;
  };
}

export interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}
