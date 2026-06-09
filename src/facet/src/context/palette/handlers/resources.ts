import { PaletteState } from '../palette.types';
import { Artifact } from '../../workspace/workspace.types';
import { readMCPResource } from '../../../api/mcp';

type ResourcesHandlerContext = {
  workspaceId: string;
};

export async function resourcesHandler(
  state: PaletteState,
  ctx: ResourcesHandlerContext,
): Promise<PaletteState> {
  const selectedResources = state.panelData.resources.resources ?? [];
  const selectedArtifacts = state.panelData.resources.artifacts ?? [];
  if (selectedResources.length === 0 && selectedArtifacts.length === 0) return state;

  // MVP guardrails
  const MAX_RESOURCES = 10;
  const MAX_CHARS_PER_RESOURCE = 12_000;

  const resources = selectedResources.slice(0, MAX_RESOURCES);

  const artifacts: Artifact[] = [];

  // Preserve any existing context artifacts (manual overrides).
  for (const c of state.panelData.context.artifacts ?? []) {
    if (!c) continue;
    artifacts.push(c);
  }

  // First: include any bundle artifacts directly.
  for (const c of selectedArtifacts) {
    if (!c) continue;
    artifacts.push(c);
  }
  for (const r of resources) {
    if (!r?.server || !r?.uri) continue;
    try {
      const contents = await readMCPResource(r.server, r.uri, ctx.workspaceId);
      const text = (contents.text ?? '').slice(0, MAX_CHARS_PER_RESOURCE);
      const title = r.title ?? contents.title ?? contents.name ?? r.uri;

      artifacts.push({
        id: `mcp:${r.server}:${r.uri}`,
        content: text,
        context: JSON.stringify({
          content_type: contents.mimeType ?? contents.contentType ?? 'text/plain',
          type: 'mcp-resource',
          title: `MCP resource • ${title}`,
          mcp: { server: r.server, uri: r.uri },
        }),
        state: 'committed',
      });
    } catch {
      artifacts.push({
        id: `mcp:${r.server}:${r.uri}:error`,
        content: '',
        context: JSON.stringify({
          content_type: 'text/plain',
          type: 'mcp-resource-error',
          title: `MCP resource • Failed to read ${r.uri}`,
          mcp: { server: r.server, uri: r.uri },
        }),
        state: 'committed',
      });
    }
  }

  // De-dupe by stringified id
  const byId = new Map<string, Artifact>();
  for (const c of artifacts) {
    const id = String(c.id ?? '');
    if (!id) continue;
    if (!byId.has(id)) byId.set(id, c);
  }
  const nextArtifacts = Array.from(byId.values());

  return {
    ...state,
    panelData: {
      ...state.panelData,
      context: {
        ...state.panelData.context,
        artifacts: nextArtifacts,
      },
    },
  };
}
