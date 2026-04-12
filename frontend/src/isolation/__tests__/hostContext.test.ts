/**
 * Tests for the MCP Apps HostContext builder.
 *
 * Verifies theme detection, locale/timezone resolution, agience extension
 * fields, and CSS variable collection from :root.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildHostContext } from '../hostContext';
import type { Artifact } from '@/context/workspace/workspace.types';

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: 'art-1',
    root_id: 'art-1',
    collection_id: 'ws-1',
    context: '{}',
    content: '',
    state: 'draft',
    ...overrides,
  } as Artifact;
}

describe('buildHostContext', () => {
  let originalMatchMedia: typeof window.matchMedia;

  beforeEach(() => {
    originalMatchMedia = window.matchMedia;
  });

  afterEach(() => {
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    }
    vi.restoreAllMocks();
  });

  it('returns a platform=web context shape', () => {
    const ctx = buildHostContext({ artifact: artifact(), workspaceId: 'ws-1' });
    expect(ctx.platform).toBe('web');
    expect(ctx.timeZone).toBeTypeOf('string');
    expect(ctx.styles?.variables).toBeDefined();
  });

  it('detects dark theme via matchMedia prefers-color-scheme', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })) as unknown as typeof window.matchMedia;

    const ctx = buildHostContext({ artifact: artifact(), workspaceId: 'ws-1' });
    expect(ctx.theme).toBe('dark');
  });

  it('falls back to light theme when matchMedia returns no match', () => {
    window.matchMedia = vi.fn().mockReturnValue({
      matches: false,
      media: '',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }) as unknown as typeof window.matchMedia;

    const ctx = buildHostContext({ artifact: artifact(), workspaceId: 'ws-1' });
    expect(ctx.theme).toBe('light');
  });

  it('carries locale from navigator.language', () => {
    const ctx = buildHostContext({ artifact: artifact(), workspaceId: 'ws-1' });
    expect(ctx.locale).toBe(navigator.language);
  });

  it('populates the agience extension with workspace + artifact ids', () => {
    const ctx = buildHostContext({
      artifact: artifact({ id: 'art-42' }),
      workspaceId: 'ws-9',
    });
    expect(ctx.agience).toEqual({
      workspaceId: 'ws-9',
      artifactId: 'art-42',
    });
  });

  it('stringifies numeric artifact ids before exposing them', () => {
    // Agience artifact ids are UUID strings in practice but the interface
    // accepts strings; cast through unknown so the test still encodes the
    // guard against non-string ids.
    const ctx = buildHostContext({
      artifact: artifact({ id: 42 as unknown as string }),
      workspaceId: 'ws-1',
    });
    expect(ctx.agience?.artifactId).toBe('42');
  });

  it('omits artifactId when artifact.id is falsy', () => {
    const ctx = buildHostContext({
      artifact: artifact({ id: '' }),
      workspaceId: 'ws-1',
    });
    expect(ctx.agience?.artifactId).toBeUndefined();
  });

  it('maps :root CSS variables into MCP standard names', () => {
    // Stub getComputedStyle to return known values.
    const fakeStyle = {
      getPropertyValue: (name: string) => {
        const values: Record<string, string> = {
          '--background': '#ffffff',
          '--foreground': '#111111',
          '--border': '#eeeeee',
        };
        return values[name] ?? '';
      },
    } as unknown as CSSStyleDeclaration;
    vi.spyOn(window, 'getComputedStyle').mockReturnValue(fakeStyle);

    const ctx = buildHostContext({ artifact: artifact(), workspaceId: 'ws-1' });
    expect(ctx.styles?.variables).toMatchObject({
      '--color-background-primary': '#ffffff',
      '--color-text-primary': '#111111',
      '--color-border-primary': '#eeeeee',
    });
    // Unmapped variables are excluded (empty strings are skipped).
    expect(ctx.styles?.variables?.['--color-background-secondary']).toBeUndefined();
  });
});
