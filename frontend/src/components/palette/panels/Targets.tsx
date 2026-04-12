import { useCallback, useMemo, useState } from 'react';

import { Collection } from '../../../context/collections/collection.types';
import { useCollections } from '../../../context/collections/CollectionsContext';
import { AGIENCE_DRAG_CONTENT_TYPE, getAgienceDragPayload, setAgienceDragData } from '../../../dnd/agienceDrag';
import { usePalette } from '../../../hooks/usePalette';

export default function TargetsPanel() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.targets;
  const { collections, isLoading } = useCollections();
  const [dragDepth, setDragDepth] = useState(0);

  const selectedSet = useMemo(() => new Set(panelState.collections.map((c) => String(c.id))), [panelState.collections]);

  const toggleTarget = useCallback(
    (item: Collection) => {
      updatePanelData('targets', (prev) => {
        const current = prev.collections;
        const exists = current.some((t) => t.id === item.id);
        const updated = exists ? current.filter((t) => t.id !== item.id) : [...current, item];
        return { ...prev, collections: updated };
      });
    },
    [updatePanelData]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragDepth(0);

      const payload = getAgienceDragPayload(e.dataTransfer);
      if (payload?.kind === 'collection') {
        toggleTarget({ id: String(payload.id), name: payload.name, description: payload.description });
      }
    },
    [toggleTarget]
  );

  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes(AGIENCE_DRAG_CONTENT_TYPE)) return;
    e.preventDefault();
    setDragDepth((prev) => prev + 1);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes(AGIENCE_DRAG_CONTENT_TYPE)) return;
    e.preventDefault();
    setDragDepth((prev) => Math.max(prev - 1, 0));
  }, []);

  const isDragActive = dragDepth > 0;

  return (
    <div
      className="w-full"
      onDrop={onDrop}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
    >
      <div
        className={
          `mb-2 overflow-hidden rounded border bg-white transition-all duration-150 ` +
          (isDragActive ? 'max-h-24 p-2 ring-2 ring-blue-500' : 'max-h-0 p-0 border-transparent')
        }
        aria-hidden={!isDragActive}
      >
        <div className="text-sm text-gray-600">Drop a collection here to toggle it</div>
      </div>

      <div className="max-h-40 overflow-y-auto">
        {isLoading && (
          <div className="px-2 py-1 text-sm text-gray-500">Loading collections…</div>
        )}
        {!isLoading && collections.length === 0 && (
          <div className="px-2 py-1 text-sm text-gray-500">No collections available.</div>
        )}

        {collections.map((target) => (
          <div
            key={target.id}
            draggable
            onDragStart={(e) => {
              setAgienceDragData(e.dataTransfer, {
                kind: 'collection',
                id: String(target.id),
                name: target.name,
                description: target.description,
              });
              e.dataTransfer.effectAllowed = 'copy';
            }}
            className="flex justify-between items-center px-2 py-1 hover:bg-gray-100 rounded"
          >
            <span className="truncate">{target.name}</span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={selectedSet.has(String(target.id))}
                onChange={() => toggleTarget(target)}
              />
              <div className="w-8 h-5 bg-gray-200 peer-checked:bg-blue-500 rounded-full transition-all duration-100" />
              <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transform peer-checked:translate-x-3 transition-transform duration-100" />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
