import { useCallback, useMemo, useRef, useState, type PropsWithChildren } from 'react';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import type { ConfirmContextValue, ConfirmOptions } from './types';
import { ConfirmContext } from './ConfirmContext';

const DEFAULT_OPTIONS: Required<Pick<ConfirmOptions, 'confirmLabel' | 'cancelLabel' | 'tone'>> = {
  confirmLabel: 'Delete',
  cancelLabel: 'Cancel',
  tone: 'danger',
};

interface DialogState {
  open: boolean;
  options: ConfirmOptions;
}

const defaultDialogState: DialogState = {
  open: false,
  options: {
    title: '',
  },
};

export function DialogProvider({ children }: PropsWithChildren) {
  const [dialogState, setDialogState] = useState<DialogState>(defaultDialogState);
  const confirmResolverRef = useRef<((value: boolean) => void) | null>(null);

  const closeDialog = useCallback((result: boolean) => {
    confirmResolverRef.current?.(result);
    confirmResolverRef.current = null;
    setDialogState(defaultDialogState);
  }, []);

  const confirm = useCallback<ConfirmContextValue['confirm']>((options) => {
    const merged: ConfirmOptions = {
      ...DEFAULT_OPTIONS,
      ...options,
    };

    return new Promise<boolean>((resolve) => {
      confirmResolverRef.current = resolve;
      setDialogState({ open: true, options: merged });
    });
  }, []);

  const value = useMemo<ConfirmContextValue>(() => ({ confirm }), [confirm]);

  const { open, options } = dialogState;
  const {
    title,
    description,
    confirmLabel = DEFAULT_OPTIONS.confirmLabel,
    cancelLabel = DEFAULT_OPTIONS.cancelLabel,
    tone = DEFAULT_OPTIONS.tone,
    icon,
    confirmIcon,
    cancelIcon,
    customContent,
    secondaryAction,
  } = options;

  const toneIcon =
    icon ??
    (tone === 'warn' ? (
      <ShieldAlert className="h-8 w-8 text-amber-500" />
    ) : (
      <AlertTriangle className="h-8 w-8 text-rose-500" />
    ));
  const confirmVariant = tone === 'warn' ? 'secondary' : 'destructive';

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            closeDialog(false);
          }
        }}
      >
        <DialogContent
          className="max-w-md"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-description"
        >
          <DialogHeader className="space-y-3">
            <div className="flex items-center gap-3">
              <span aria-hidden="true">{toneIcon}</span>
              <DialogTitle id="confirm-dialog-title" className="text-left">
                {title || (tone === 'warn' ? 'Are you sure?' : 'Delete item?')}
              </DialogTitle>
            </div>
            {description ? (
              <DialogDescription id="confirm-dialog-description" className="text-left">
                {description}
              </DialogDescription>
            ) : null}
          </DialogHeader>

          {customContent}

          <DialogFooter className="mt-6">
            {secondaryAction ? (
              <Button
                variant="ghost"
                onClick={() => {
                  closeDialog(false);
                  secondaryAction.onAction();
                }}
              >
                {secondaryAction.label}
              </Button>
            ) : null}
            <Button variant="outline" onClick={() => closeDialog(false)}>
              {cancelIcon}
              {cancelLabel}
            </Button>
            <Button variant={confirmVariant} onClick={() => closeDialog(true)}>
              {confirmIcon}
              {confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}
