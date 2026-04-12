import { normalizeContentType } from './content-type';

export type ArtifactContext = {
  content_type?: string;
  type?: string;
  title?: string;
  filename?: string;
  description?: string;
  tags?: string[];
  uri?: string;
  bytes?: number;
  size?: number;
  upload?: { status?: string; progress?: number; error?: string };
  // View and container metadata (forward-looking fields)
  target?: { kind?: string; id?: string; collection_id?: string };
  view?: { mode?: string; target?: { kind?: string; id?: string; collection_id?: string } };
  collection_id?: string;
  target_collection_id?: string;
  name?: string;
  summary?: string;
  [key: string]: unknown;
};

export function safeParseArtifactContext(raw: unknown): ArtifactContext {
  if (!raw) return {};

  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as ArtifactContext;
  }

  if (typeof raw !== 'string') {
    return { title: String(raw) };
  }

  const text = raw.trim();
  if (!text) return {};

  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as ArtifactContext;
    }
    return { title: text };
  } catch {
    return { title: text, content_type: 'text/plain' };
  }
}

export function stringifyArtifactContext(ctx: unknown): string {
  if (typeof ctx === 'string') {
    // If it's already JSON, keep it. Otherwise, wrap as a text/plain context.
    const trimmed = ctx.trim();
    if (!trimmed) return JSON.stringify({ content_type: 'text/plain', title: '' });
    try {
      JSON.parse(trimmed);
      return trimmed;
    } catch {
      return JSON.stringify({ content_type: 'text/plain', title: trimmed });
    }
  }

  if (ctx && typeof ctx === 'object' && !Array.isArray(ctx)) {
    return JSON.stringify(ctx);
  }

  return JSON.stringify({ content_type: 'text/plain', title: '' });
}

export function getContextContentType(ctx: ArtifactContext): string | undefined {
  const raw = typeof ctx.content_type === 'string' ? ctx.content_type : undefined;
  return normalizeContentType(raw);
}
