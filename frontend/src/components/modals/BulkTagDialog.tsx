import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';

export interface BulkTagApplyRequest {
  tags: string[];
  replaceExisting: boolean;
}

interface BulkTagDialogProps {
  open: boolean;
  onClose: () => void;
  onApply: (request: BulkTagApplyRequest) => void | Promise<void>;
  selectedCount: number;
}

function normalizeTags(tags: string[]): string[] {
  return Array.from(new Set(tags.map((tag) => tag.trim()).filter(Boolean)));
}

export function BulkTagDialog({ open, onClose, onApply, selectedCount }: BulkTagDialogProps) {
  const [tags, setTags] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTags([]);
    setInput('');
    setReplaceExisting(false);
  }, [open]);

  const addTag = (value: string) => {
    const next = value.trim();
    if (!next) return;
    setTags((prev) => normalizeTags([...prev, next]));
    setInput('');
  };

  const removeTag = (value: string) => {
    setTags((prev) => prev.filter((tag) => tag !== value));
  };

  const handleApply = async () => {
    const normalized = normalizeTags(tags);
    if (!replaceExisting && normalized.length === 0) return;
    await onApply({ tags: normalized, replaceExisting });
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk Tags</DialogTitle>
          <DialogDescription>
            Update tags for {selectedCount} selected artifacts. Add tags to merge them, or switch modes to replace existing tags.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {tags.length === 0 && (
              <span className="text-sm text-gray-500">No tags queued yet.</span>
            )}
            {tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-full border border-gray-300 bg-white px-2 py-1 text-xs"
              >
                {tag}
                <button
                  type="button"
                  className="text-gray-500 hover:text-gray-800"
                  onClick={() => removeTag(tag)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <input
            className="w-full rounded border border-gray-300 p-2 text-sm"
            placeholder="Type a tag and press Enter or comma"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                addTag(input);
              }
              if (e.key === 'Backspace' && input === '' && tags.length > 0) {
                setTags((prev) => prev.slice(0, -1));
              }
            }}
            onBlur={() => addTag(input)}
          />

          <label className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={replaceExisting}
              onChange={(e) => setReplaceExisting(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Replace existing tags on the selected artifacts.
              {!replaceExisting && ' Leave this off to merge the new tags with what each artifact already has.'}
            </span>
          </label>
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!replaceExisting && tags.length === 0}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {replaceExisting ? 'Apply Tags' : 'Add Tags'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BulkTagDialog;