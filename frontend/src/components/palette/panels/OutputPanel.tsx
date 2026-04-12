import { useCallback, useState } from 'react';

import { usePalette } from '../../../hooks/usePalette';
import { useWorkspace } from '../../../hooks/useWorkspace';
import CardGrid from '../../common/CardGrid';
import { getAgienceDragPayload, getDroppedArtifactIds, isAgienceDrag } from '../../../dnd/agienceDrag';

export default function OutputPanel() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.output;
  const { artifacts: workspaceArtifacts } = useWorkspace();
  const [dragDepth, setDragDepth] = useState(0);

  const addArtifactFromWorkspace = useCallback(
    (id: string) => {
      const artifact = workspaceArtifacts.find((c) => String(c.id) === String(id));
      if (!artifact) return;
      updatePanelData('output', (prev) => {
        if (prev.artifacts.some((c) => String(c.id) === String(artifact.id))) return prev;
        return { ...prev, artifacts: [...prev.artifacts, artifact] };
      });
    },
    [updatePanelData, workspaceArtifacts]
  );

  const addTextArtifact = useCallback(
    (content: string, context: string) => {
      const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? `output-${crypto.randomUUID()}`
        : `output-${Date.now()}-${Math.random().toString(16).slice(2)}`;

      updatePanelData('output', (prev) => ({
        ...prev,
        artifacts: [
          ...prev.artifacts,
          {
            id,
            context,
            content,
            state: 'committed',
            collection_ids: [],
          },
        ],
      }));
    },
    [updatePanelData]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      if (!isAgienceDrag(e.dataTransfer)) return;
      e.preventDefault();
      e.stopPropagation();
      setDragDepth(0);

      const payload = getAgienceDragPayload(e.dataTransfer);
      if (payload?.kind === 'prompt' && payload.body) {
        addTextArtifact(payload.body, payload.name ? `Prompt: ${payload.name}` : 'Prompt');
        return;
      }
      if (payload?.kind === 'text' && payload.text) {
        addTextArtifact(payload.text, 'Text');
        return;
      }

      const ids = getDroppedArtifactIds(e.dataTransfer);
      if (ids.length) ids.forEach((id) => addArtifactFromWorkspace(id));
    },
    [addArtifactFromWorkspace, addTextArtifact]
  );

  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!isAgienceDrag(e.dataTransfer)) return;
    e.preventDefault();
    setDragDepth((prev) => prev + 1);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    if (!isAgienceDrag(e.dataTransfer)) return;
    e.preventDefault();
    setDragDepth((prev) => Math.max(prev - 1, 0));
  }, []);

  const isDragActive = dragDepth > 0;

  return (
    <div
      className={
        `w-full p-4 rounded border bg-white ` +
        (isDragActive ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-300')
      }
      onDrop={onDrop}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
    >
      <CardGrid 
        artifacts={panelState.artifacts}
        selectable={false}
        draggable={false}
        editable={false}
      />
    </div>
  );
}
