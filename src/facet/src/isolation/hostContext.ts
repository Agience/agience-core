/**
 * Assembles MCP Apps HostContext from Agience platform state.
 *
 * Spec reference: SEP-1865 Section 3 — ui/initialize response.
 */

import type { Artifact } from '@/context/workspace/workspace.types';

export interface HostContext {
  theme?: 'light' | 'dark';
  locale?: string;
  timeZone?: string;
  platform?: 'web' | 'desktop' | 'mobile';
  containerDimensions?: { maxHeight?: number; maxWidth?: number };
  styles?: {
    variables?: Record<string, string>;
  };
  // Agience-specific extensions
  agience?: {
    workspaceId?: string;
    artifactId?: string;
  };
}

interface BuildHostContextOptions {
  artifact: Artifact;
  workspaceId: string;
}

/**
 * Build a HostContext object from current platform state.
 */
export function buildHostContext({ artifact, workspaceId }: BuildHostContextOptions): HostContext {
  const prefersDark = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;

  return {
    theme: prefersDark ? 'dark' : 'light',
    locale: typeof navigator !== 'undefined' ? navigator.language : 'en-US',
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    platform: 'web',
    styles: {
      variables: collectCssVariables(),
    },
    agience: {
      workspaceId,
      artifactId: artifact.id ? String(artifact.id) : undefined,
    },
  };
}

/**
 * Collect a subset of CSS custom properties from :root to pass to the View.
 * Maps Tailwind/Agience theme variables to MCP Apps standard variable names.
 */
function collectCssVariables(): Record<string, string> {
  if (typeof document === 'undefined') return {};

  const style = getComputedStyle(document.documentElement);
  const vars: Record<string, string> = {};

  // Map common CSS variables that views might need for theming
  const mappings: Record<string, string> = {
    '--background': '--color-background-primary',
    '--foreground': '--color-text-primary',
    '--muted': '--color-background-secondary',
    '--muted-foreground': '--color-text-secondary',
    '--border': '--color-border-primary',
    '--ring': '--color-ring-focus',
    '--radius': '--border-radius-md',
  };

  for (const [src, dst] of Object.entries(mappings)) {
    const value = style.getPropertyValue(src).trim();
    if (value) {
      vars[dst] = value;
    }
  }

  return vars;
}
