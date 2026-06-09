import { useCallback, useMemo, useState } from 'react';

import { Artifact } from '../../../context/workspace/workspace.types';
import { usePalette } from '../../../hooks/usePalette';
import { useWorkspace } from '../../../hooks/useWorkspace';
import CardGrid from '../../common/CardGrid';
import { getAgienceDragPayload, getDroppedArtifactIds, isAgienceDrag } from '../../../dnd/agienceDrag';

export default function Prompts() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.prompts;
  const { artifacts: workspaceArtifacts } = useWorkspace();
  const [dragDepth, setDragDepth] = useState(0);

  const handleSelect = (artifact: Artifact) => {
    updatePanelData("prompts", (prev) => ({
      ...prev,
      selectedId: artifact.id,
    }));

    updatePanelData("instructions", (prev) => ({
      ...prev,
      text: artifact.content,
    }));
  };

  const validArtifacts = useMemo(() => panelState.artifacts.filter(
    (c): c is Artifact =>
      typeof c === "object" &&
      c !== null &&
      "id" in c &&
      "content" in c
  ), [panelState.artifacts]);

  const addPromptArtifact = useCallback(
    (content: string, context: string) => {
      const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? `prompt-${crypto.randomUUID()}`
        : `prompt-${Date.now()}-${Math.random().toString(16).slice(2)}`;

      const newArtifact: Artifact = {
        id,
        context,
        content,
        state: 'committed',
      };

      updatePanelData('prompts', (prev) => ({
        ...prev,
        artifacts: [...prev.artifacts, newArtifact],
        selectedId: id,
      }));

      updatePanelData('instructions', (prev) => ({
        ...prev,
        text: content,
      }));
    },
    [updatePanelData]
  );

  const addArtifactFromWorkspace = useCallback(
    (id: string) => {
      const artifact = workspaceArtifacts.find((c) => String(c.id) === String(id));
      if (!artifact) return;
      updatePanelData('prompts', (prev) => {
        const existing = prev.artifacts;
        if (existing.some((c) => String(c.id) === String(artifact.id))) {
          return { ...prev, selectedId: String(artifact.id) };
        }
        return { ...prev, artifacts: [...existing, artifact], selectedId: String(artifact.id) };
      });
      updatePanelData('instructions', (prev) => ({ ...prev, text: artifact.content }));
    },
    [updatePanelData, workspaceArtifacts]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      if (!isAgienceDrag(e.dataTransfer)) return;
      e.preventDefault();
      e.stopPropagation();
      setDragDepth(0);

      const payload = getAgienceDragPayload(e.dataTransfer);
      if (payload?.kind === 'prompt' && payload.body) {
        addPromptArtifact(payload.body, payload.name ? `Prompt: ${payload.name}` : 'Prompt');
        return;
      }

      if (payload?.kind === 'text' && payload.text) {
        addPromptArtifact(payload.text, 'Text');
        return;
      }

      const ids = getDroppedArtifactIds(e.dataTransfer);
      if (ids.length) ids.forEach((id) => addArtifactFromWorkspace(id));
    },
    [addArtifactFromWorkspace, addPromptArtifact]
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
      onDrop={onDrop}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
      className={
        `w-full min-h-[151px] rounded border bg-white resize-y overflow-auto p-2 ` +
        (isDragActive ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-300')
      }
    >
      <CardGrid
        artifacts={validArtifacts}
        isSelected={(id) => id === panelState.selectedId}
        selectable
        draggable={false}
        editable={false}
        onArtifactMouseDown={(id) => {
          const artifact = validArtifacts.find((c) => String(c.id) === String(id));
          if (artifact) handleSelect(artifact);
        }}
      />
    </div>
  );
}
