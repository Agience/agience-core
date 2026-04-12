// Centralized type -> color mapping and helpers

export type SourceType = 'resources' | 'tools' | 'prompts' | 'workspace';

// Tailwind utility class tokens and hex values for runtime styles
export const TYPE_COLORS: Record<SourceType, {
  bg50: string;
  text700: string;
  ring300: string;
  border500: string;
  solid500: string;
}> = {
  resources: {
    bg50: 'bg-blue-50',
    text700: 'text-blue-700',
    ring300: 'ring-blue-300',
    border500: 'border-blue-500',
    solid500: '#3b82f6',
  },
  tools: {
    bg50: 'bg-orange-50',
    text700: 'text-orange-700',
    ring300: 'ring-orange-300',
    border500: 'border-orange-500',
    solid500: '#f59e0b',
  },
  prompts: {
    bg50: 'bg-green-50',
    text700: 'text-green-700',
    ring300: 'ring-green-300',
    border500: 'border-green-500',
    solid500: '#10b981',
  },
  workspace: {
    bg50: 'bg-purple-50',
    text700: 'text-purple-700',
    ring300: 'ring-purple-300',
    border500: 'border-purple-500',
    solid500: '#8b5cf6',
  },
};

// Infer a broad source type for an artifact when possible
export function inferSourceType(opts: {
  activeSourceType?: 'workspace' | 'collection' | 'mcp-server' | null;
  contextType?: string | undefined; // e.g. 'mcp-tool' | 'mcp-prompt'
}): SourceType {
  if (opts.activeSourceType === 'collection') return 'resources';
  if (opts.activeSourceType === 'mcp-server') {
    if (opts.contextType === 'mcp-tool') return 'tools';
    if (opts.contextType === 'mcp-prompt') return 'prompts';
  }
  return 'workspace';
}
