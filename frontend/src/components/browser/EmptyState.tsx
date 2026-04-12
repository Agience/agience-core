// frontend/src/components/browser/EmptyState.tsx
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  type: 'no-artifacts' | 'no-search-results' | 'no-source';
  searchQuery?: string;
  onClearSearch?: () => void;
}

export default function EmptyState({ type }: EmptyStateProps) {

  if (type === 'no-source') {
    return (
      <div className="flex h-full items-center justify-center px-6 py-12">
        <div className="w-full max-w-2xl rounded-2xl border border-dashed border-slate-300 bg-white px-8 py-12 text-center shadow-sm">
          <Inbox className="mx-auto mb-4 h-16 w-16 text-slate-300" />
          <p className="text-lg font-semibold text-slate-900">No workspace docked</p>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-600">
            Click + to create and dock a workspace, or drag and drop search results here to create one from them. You can also find one to dock. Hint: try searching for "Inbox"
          </p>
        </div>
      </div>
    );
  }

  // no-cards
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center gap-2 text-gray-500">
      <p className="font-medium">Nothing Here</p>
      <p className="text-xs">
        Double-click an empty space or drop a file to create a new card.
      </p>
    </div>
  );
}
