export const AGIENCE_DRAG_CONTENT_TYPE = 'application/vnd.agience.drag+json';

export type AgienceDragPayload =
  | { kind: 'artifacts'; ids: string[]; orderedIds?: string[]; source?: { kind: string; id: string } }
  | { kind: 'collection'; id: string; name?: string; description?: string }
  | { kind: 'tool'; server: string; tool_name: string; title?: string }
  | { kind: 'resource'; server: string; uri: string; title?: string; contentType?: string; resourceKind?: string }
  | { kind: 'prompt'; prompt_id: string; name?: string; contentType?: string; body?: string }
  | { kind: 'text'; text: string };

function safeJsonParse<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function setAgienceDragData(dt: DataTransfer, payload: AgienceDragPayload) {
  dt.setData(AGIENCE_DRAG_CONTENT_TYPE, JSON.stringify(payload));

  // Convenience fallbacks for cross-app interop
  if (payload.kind === 'artifacts') {
    dt.setData('application/json', JSON.stringify({ ids: payload.ids, orderedIds: payload.orderedIds }));
    dt.setData('text/plain', (payload.orderedIds ?? payload.ids).join(','));
  } else if (payload.kind === 'collection') {
    dt.setData('application/json', JSON.stringify({ kind: 'collection', id: payload.id, name: payload.name }));
    dt.setData('text/plain', payload.name ?? payload.id);
  } else if (payload.kind === 'tool') {
    dt.setData('text/plain', payload.tool_name);
  } else if (payload.kind === 'resource') {
    dt.setData('text/plain', payload.uri);
  } else if (payload.kind === 'prompt') {
    dt.setData('text/plain', payload.name ?? payload.prompt_id);
  } else if (payload.kind === 'text') {
    dt.setData('text/plain', payload.text);
  }
}

export function getAgienceDragPayload(dt: DataTransfer | null | undefined): AgienceDragPayload | null {
  if (!dt) return null;

  const raw = dt.getData(AGIENCE_DRAG_CONTENT_TYPE);
  if (raw) {
    const parsed = safeJsonParse<AgienceDragPayload>(raw);
    if (parsed && typeof parsed === 'object' && 'kind' in parsed) return parsed;
  }

  // Generic JSON fallback
  const jsonRaw = dt.getData('application/json');
  if (jsonRaw) {
    const parsed = safeJsonParse<{ ids?: unknown; id?: unknown; kind?: unknown; name?: unknown; text?: unknown }>(jsonRaw);
    if (parsed?.kind === 'collection' && parsed?.id) {
      return { kind: 'collection', id: String(parsed.id), name: parsed?.name ? String(parsed.name) : undefined };
    }

    const ids = Array.isArray(parsed?.ids)
      ? parsed?.ids.map(String)
      : parsed?.id
        ? [String(parsed.id)]
        : [];
    if (ids.length) return { kind: 'artifacts', ids };

    if (typeof parsed?.text === 'string' && parsed.text) {
      return { kind: 'text', text: parsed.text };
    }
  }

  // Text fallback
  const textRaw = dt.getData('text/plain');
  if (textRaw) {
    return { kind: 'text', text: textRaw };
  }

  return null;
}

export function getDroppedArtifactIds(dt: DataTransfer | null | undefined): string[] {
  const payload = getAgienceDragPayload(dt);
  return payload?.kind === 'artifacts' ? payload.ids : [];
}

export function getDroppedText(dt: DataTransfer | null | undefined): string {
  const payload = getAgienceDragPayload(dt);
  if (!payload) return '';
  if (payload.kind === 'text') return payload.text ?? '';
  if (payload.kind === 'prompt') return payload.body ?? '';
  return '';
}

export function getDroppedCollection(dt: DataTransfer | null | undefined): { id: string; name?: string } | null {
  const payload = getAgienceDragPayload(dt);
  if (payload?.kind !== 'collection') return null;
  return { id: payload.id, name: payload.name };
}

export function isAgienceDrag(dt: DataTransfer | null | undefined): boolean {
  if (!dt?.types) return false;
  const types = Array.from(dt.types);
  return types.includes(AGIENCE_DRAG_CONTENT_TYPE) || types.includes('application/json') || types.includes('text/plain');
}
