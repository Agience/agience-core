import { FiX, FiTag, FiFolder, FiTrash2, FiArchive, FiLogOut } from 'react-icons/fi';

interface MultiCardToolbarProps {
  selectedCount: number;
  onArchive: () => void;
  onAddTags: () => void;
  onMove: () => void;
  moveLabel?: string;
  onDelete: () => void;
  onDrop: () => void;
  onClear: () => void;
  hasNew: boolean;
  hasCommitted: boolean;
}

export default function MultiCardToolbar({
  selectedCount,
  onArchive,
  onAddTags,
  onMove,
  moveLabel = 'Move',
  onDelete,
  onDrop,
  onClear,
  hasNew,
  hasCommitted,
}: MultiCardToolbarProps) {
  return (
    <div className="fixed bottom-6 inset-x-0 flex justify-center z-50 pointer-events-none">
      <div className="pointer-events-auto flex items-center gap-1 px-4 py-2 bg-white rounded-full shadow-lg border border-gray-200">
        <span className="text-sm font-medium text-gray-700 px-2">
          {selectedCount} selected
        </span>

        <div className="w-px h-6 bg-gray-200 mx-1" />

        {hasCommitted && (
          <button
            onClick={onArchive}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
          >
            <FiArchive className="w-4 h-4" />
            Archive
          </button>
        )}

        <button
          onClick={onAddTags}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
        >
          <FiTag className="w-4 h-4" />
          Add Tags
        </button>

        <button
          onClick={onMove}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
        >
          <FiFolder className="w-4 h-4" />
          {moveLabel}
        </button>

        {hasCommitted && (
          <button
            onClick={onDrop}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
          >
            <FiLogOut className="w-4 h-4" />
            Drop
          </button>
        )}

        {hasNew && (
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 rounded-full transition-colors"
          >
            <FiTrash2 className="w-4 h-4" />
            Delete
          </button>
        )}

        <div className="w-px h-6 bg-gray-200 mx-1" />

        <button
          onClick={onClear}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
          title="Clear selection"
        >
          <FiX className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
