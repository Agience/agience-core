import { useCallback, useMemo, useState } from 'react';
import { usePalette } from '../../../hooks/usePalette';
import { useWorkspace } from '../../../hooks/useWorkspace';
import CardGrid from '../../common/CardGrid';
import { getAgienceDragPayload, getDroppedArtifactIds, isAgienceDrag } from '../../../dnd/agienceDrag';

export default function KnowledgePanel() {
  const { state, updatePanelData } = usePalette();
  const { artifacts } = useWorkspace();
  const [dragDepth, setDragDepth] = useState(0);

  const panelState = state.panelData.knowledge;
  const selectedTools = state.panelData.tools.tools;

  const selectedToolSet = useMemo(() => new Set(selectedTools.map(String)), [selectedTools]);

  const toggleTool = useCallback(
    (toolName: string) => {
      const name = String(toolName || '').trim();
      if (!name) return;
      updatePanelData('tools', (prev) => {
        const next = new Set((prev.tools ?? []).map(String));
        if (next.has(name)) next.delete(name);
        else next.add(name);
        return { ...prev, tools: Array.from(next) };
      });
    },
    [updatePanelData]
  );

  const addArtifactFromWorkspace = useCallback((id: string) => {
    const artifact = artifacts.find(c => String(c.id) === String(id));
    if (!artifact) return;

    updatePanelData('knowledge', (prev) => {
      const existing = prev.artifacts;
      if (existing.some(c => String(c.id) === String(artifact.id))) return prev;
      return { ...prev, artifacts: [...existing, artifact] };
    });
  }, [artifacts, updatePanelData]);

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!isAgienceDrag(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    setDragDepth(0);

    const payload = getAgienceDragPayload(e.dataTransfer);
    if (payload?.kind === 'tool') {
      toggleTool(payload.tool_name);
      return;
    }

    if (payload?.kind === 'text' && payload.text) {
      toggleTool(payload.text);
      return;
    }

    const ids = getDroppedArtifactIds(e.dataTransfer);
    if (ids.length) ids.forEach((id) => addArtifactFromWorkspace(id));
  }, [addArtifactFromWorkspace, toggleTool]);

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragDepth(prev => prev + 1);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragDepth(prev => Math.max(prev - 1, 0));
  }, []);

  const removeArtifact = useCallback((id: string) => {
    updatePanelData('knowledge', (prev) => {
      const existing = prev.artifacts;
      return { ...prev, artifacts: existing.filter(c => String(c.id) !== id) };
    });
  }, [updatePanelData]);

  const isDragActive = dragDepth > 0;

  return (
    <div className="space-y-3">
      <div className="rounded border bg-white p-2">
        <div className="text-xs font-semibold text-gray-600 mb-1">Selected tools</div>
        {selectedTools.length === 0 ? (
          <div className="text-sm text-gray-500">No tools selected.</div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {selectedTools.map((t) => (
              <button
                key={t}
                className={
                  'text-xs px-2 py-0.5 rounded border ' +
                  (selectedToolSet.has(String(t)) ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-700 border-gray-300')
                }
                onClick={() => toggleTool(String(t))}
                title="Click to toggle"
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      <div
        onDrop={onDrop}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={e => e.preventDefault()}
        className={`w-full min-h-[151px] rounded border bg-white resize-y overflow-auto
          ${isDragActive ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-300'}`}
      >
        <CardGrid
          artifacts={panelState.artifacts}
          selectable={false}
          draggable={false}
          editable={false}
          onRemove={artifact => artifact.id && removeArtifact(String(artifact.id))}
        />
      </div>
    </div>
  );
}
