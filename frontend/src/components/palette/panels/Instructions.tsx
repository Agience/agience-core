import { useCallback, useRef, useState } from 'react';
import { usePalette } from '../../../hooks/usePalette';
import { useWorkspace } from '../../../hooks/useWorkspace';
import CardGrid from '../../common/CardGrid';
import { getAgienceDragPayload, getDroppedArtifactIds } from '../../../dnd/agienceDrag';

export default function InstructionsPanel() {
  const { state, updatePanelData } = usePalette();
  const { artifacts: workspaceArtifacts } = useWorkspace();
  const [dragDepth, setDragDepth] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const panelState = state.panelData.instructions;

  const addArtifact = useCallback(
    (id: string) => {
      const artifact = workspaceArtifacts.find((c) => String(c.id) === id);
      if (!artifact) return;

      updatePanelData('instructions', (prev) => {
        const existing = prev.artifacts;
        if (existing.some((c) => c.id === artifact.id)) return prev;
        return { ...prev, artifacts: [...existing, artifact] };
      });
    },
    [workspaceArtifacts, updatePanelData]
  );

  const removeArtifact = useCallback(
    (id: string) => {
      updatePanelData('instructions', (prev) => {
        const existing = prev.artifacts;
        return { ...prev, artifacts: existing.filter((c) => c.id !== id) };
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
      if (payload?.kind === 'prompt' && payload.body) {
        updatePanelData('instructions', (prev) => ({
          ...prev,
          text: prev.text ? `${prev.text}\n\n${payload.body}` : payload.body ?? '',
        }));
        return;
      }

      if (payload?.kind === 'text' && payload.text) {
        updatePanelData('instructions', (prev) => ({
          ...prev,
          text: prev.text ? `${prev.text}\n${payload.text}` : payload.text,
        }));
        return;
      }

      const ids = getDroppedArtifactIds(e.dataTransfer);
      if (ids.length) ids.forEach((id) => addArtifact(id));
    },
    [addArtifact, updatePanelData]
  );

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragDepth((prev) => prev + 1);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragDepth((prev) => Math.max(prev - 1, 0));
  }, []);

  const isDragActive = dragDepth > 0;

  return (
    <div className="space-y-4">
      <div className="rounded border bg-white p-2">
        <div className="text-xs font-semibold text-gray-600 mb-1">Instruction text</div>
        <textarea
          ref={textareaRef}
          className="w-full min-h-[96px] resize-y rounded border border-gray-200 p-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="What should happen? (You can also drop prompts/text/artifacts)"
          value={panelState.text}
          onChange={(e) =>
            updatePanelData('instructions', (prev) => ({
              ...prev,
              text: e.target.value,
            }))
          }
        />
      </div>

      <div
        onDrop={onDrop}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => textareaRef.current?.focus()}
        className={`w-full min-h-[151px] rounded border bg-white resize-y overflow-auto p-2
          ${isDragActive ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-300'}
        `}
      >
        <CardGrid
          artifacts={panelState.artifacts}
          selectable={false}
          draggable={false}
          editable={false}
          onRemove={(artifact) => artifact.id && removeArtifact(String(artifact.id))}
        />
      </div>
    </div>
  );
}
