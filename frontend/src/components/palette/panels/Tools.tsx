import { useCallback, useEffect, useMemo, useState } from 'react';
import { listWorkspaceMCPServers, type MCPTool } from '../../../api/mcp';
import { useWorkspaces } from '../../../context/workspaces/WorkspacesContext';
import { AGIENCE_DRAG_CONTENT_TYPE, getAgienceDragPayload, setAgienceDragData } from '../../../dnd/agienceDrag';
import { useWorkspace } from '../../../hooks/useWorkspace';
import { usePalette } from '../../../hooks/usePalette';

export default function ToolsPanel() {
  const { state, updatePanelData } = usePalette();
  const panelState = state.panelData.tools;
  const { artifacts: workspaceArtifacts } = useWorkspace();
  const { activeWorkspace } = useWorkspaces();
  const workspaceId = activeWorkspace?.id ?? '';

  const [dragDepth, setDragDepth] = useState(0);
  const [loading, setLoading] = useState(false);
  const [tools, setTools] = useState<Array<{ server: string; tool: MCPTool }>>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!workspaceId) {
        setTools([]);
        return;
      }
      setLoading(true);
      try {
        const servers = await listWorkspaceMCPServers(workspaceId);
        if (cancelled) return;
        const flattened = servers.flatMap((s) => (s.tools ?? []).map((t) => ({ server: s.server, tool: t })));
        setTools(flattened);
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to list workspace MCP tools', err);
          setTools([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const toggleTool = useCallback(
    (toolName: string) => {
      updatePanelData('tools', (prev) => {
        const selected = new Set(prev.tools);
        if (selected.has(toolName)) selected.delete(toolName);
        else selected.add(toolName);
        return { ...prev, tools: Array.from(selected) };
      });
    },
    [updatePanelData]
  );

  const selectedSet = useMemo(() => new Set(panelState.tools), [panelState.tools]);

  const knownToolNames = useMemo(() => {
    return new Set(tools.map((t) => t.tool.name));
  }, [tools]);

  const extractToolCandidates = useCallback(
    (raw: string) => {
      const tokens = raw
        .split(/[\s,;]+/g)
        .map((t) => t.trim())
        .filter(Boolean)
        .flatMap((t) => {
          const parts = t.split('::');
          return parts.length > 1 ? [parts[parts.length - 1]] : [t];
        });

      const hits: string[] = [];
      for (const t of tokens) {
        if (knownToolNames.has(t)) hits.push(t);
      }
      return Array.from(new Set(hits));
    },
    [knownToolNames]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragDepth(0);

      const payload = getAgienceDragPayload(e.dataTransfer);
      if (payload?.kind === 'tool') {
        toggleTool(payload.tool_name);
        return;
      }

      if (payload?.kind === 'text' && payload.text) {
        const candidates = extractToolCandidates(payload.text);
        if (candidates.length) candidates.forEach(toggleTool);
        else toggleTool(payload.text);
        return;
      }

      if (payload?.kind === 'artifacts') {
        const ids = payload.ids ?? [];
        const texts = ids
          .map((id) => workspaceArtifacts.find((c) => String(c.id) === String(id)))
          .filter(Boolean)
          .map((c) => `${c?.context ?? ''}\n${c?.content ?? ''}`);
        const candidates = extractToolCandidates(texts.join('\n'));
        if (candidates.length) candidates.forEach(toggleTool);
      }
    },
    [extractToolCandidates, toggleTool, workspaceArtifacts]
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
        <div className="text-sm text-gray-600">Drop a tool here to toggle it</div>
      </div>

      <div className="max-h-40 overflow-y-auto">
        {!workspaceId && (
          <div className="px-2 py-1 text-sm text-gray-500">Select a workspace to view tools.</div>
        )}
        {workspaceId && loading && (
          <div className="px-2 py-1 text-sm text-gray-500">Loading tools…</div>
        )}
        {workspaceId && !loading && tools.length === 0 && (
          <div className="px-2 py-1 text-sm text-gray-500">No tools available.</div>
        )}

        {tools.map(({ server, tool }) => {
          const key = `${server}::${tool.name}`;
          const checked = selectedSet.has(tool.name);
          return (
            <div
              key={key}
              draggable
              onDragStart={(e) => {
                setAgienceDragData(e.dataTransfer, {
                  kind: 'tool',
                  server,
                  tool_name: tool.name,
                  title: tool.description,
                });
                e.dataTransfer.effectAllowed = 'copy';
              }}
              className="flex justify-between items-center px-2 py-1 hover:bg-gray-100 rounded"
              title={`${server} • ${tool.name}`}
            >
              <span className="truncate">{tool.name}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={checked}
                  onChange={() => toggleTool(tool.name)}
                />
                <div className="w-8 h-5 bg-gray-200 peer-checked:bg-blue-500 rounded-full transition-all duration-100" />
                <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transform peer-checked:translate-x-3 transition-transform duration-100" />
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
