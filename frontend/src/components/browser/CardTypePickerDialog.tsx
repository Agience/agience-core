import { useMemo } from 'react';

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { getCreatableTypes } from '@/registry/content-types';

type CardTypePickerDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (contentType: string) => void;
};

export default function CardTypePickerDialog({
  open,
  onOpenChange,
  onSelect,
}: CardTypePickerDialogProps) {
  const creatableTypes = useMemo(() => {
    return getCreatableTypes()
      .filter((type) => !type.content_type.includes('*'))
      .sort((left, right) => left.label.localeCompare(right.label));
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Create Card</DialogTitle>
          <DialogDescription>
            Pick an artifact type to create.
          </DialogDescription>
        </DialogHeader>

        <div className="grid max-h-[60vh] gap-3 overflow-y-auto pr-1 sm:grid-cols-2 lg:grid-cols-3">
          {creatableTypes.map((type) => {
            const TypeIcon = type.icon;
            return (
              <button
                key={type.content_type}
                type="button"
                onClick={() => onSelect(type.content_type)}
                className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left transition-colors hover:border-slate-400 hover:bg-slate-50"
              >
                <div
                  className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${type.color}20`, color: type.color }}
                >
                  <TypeIcon size={18} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-slate-900">{type.label}</div>
                  <div className="mt-1 break-all text-xs text-slate-500">{type.content_type}</div>
                </div>
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}