import { describe, expect, it } from 'vitest';

import { safeParseArtifactContext, stringifyArtifactContext } from '../artifactContext';

describe('artifactContext', () => {
  it('safeParseArtifactContext parses JSON objects', () => {
    const ctx = safeParseArtifactContext(JSON.stringify({ title: 'T', content_type: 'text/plain' }));
    expect(ctx.title).toBe('T');
    expect(ctx.content_type).toBe('text/plain');
  });

  it('safeParseArtifactContext wraps legacy string context', () => {
    const ctx = safeParseArtifactContext('Legacy title');
    expect(ctx.title).toBe('Legacy title');
    expect(ctx.content_type).toBe('text/plain');
  });

  it('stringifyArtifactContext keeps JSON strings as-is', () => {
    const raw = JSON.stringify({ title: 'Ok', content_type: 'text/plain' });
    expect(stringifyArtifactContext(raw)).toBe(raw);
  });

  it('stringifyArtifactContext wraps legacy strings into JSON', () => {
    const raw = stringifyArtifactContext('Hello');
    const parsed = JSON.parse(raw) as { title?: string; content_type?: string };
    expect(parsed.title).toBe('Hello');
    expect(parsed.content_type).toBe('text/plain');
  });
});
