export const AGENCY_CONTENT_TYPE = 'application/vnd.agience.agency+json';
export const TRANSFORM_CONTENT_TYPE = 'application/vnd.agience.transform+json';
export const CHAT_CONTENT_TYPE = 'application/vnd.agience.chat+json';

// Root containers
export const TOOL_CONTENT_TYPE = 'application/vnd.agience.tool+json';
export const RESOURCES_CONTENT_TYPE = 'application/vnd.agience.resources+json';
export const PROMPTS_CONTENT_TYPE = 'application/vnd.agience.prompts+json';

// References / boundaries
export const WORKSPACE_CONTENT_TYPE = 'application/vnd.agience.workspace+json';
export const COLLECTION_CONTENT_TYPE = 'application/vnd.agience.collection+json';

export function normalizeContentType(contentType?: string): string | undefined {
  if (!contentType) return undefined;
  const base = contentType.split(';')[0]?.trim();
  return base ? base.toLowerCase() : undefined;
}

export function getEffectiveContentType(args: { contentType?: string }): string | undefined {
  return normalizeContentType(args.contentType);
}
