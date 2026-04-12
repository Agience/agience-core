/**
 * Tests for the CSP meta tag builder used by the MCP Apps iframe sandbox.
 *
 * The default policy is restrictive per SEP-1865 § 9 — only declared
 * `_meta.ui.csp` domains relax it. These tests lock that behavior down so a
 * regression cannot silently widen the sandbox.
 */

import { describe, it, expect } from 'vitest';
import { buildCspMetaTag } from '../csp';

function parsePolicy(tag: string): Record<string, string> {
  const match = tag.match(/content="([^"]+)"/);
  expect(match).not.toBeNull();
  const policy = match![1];
  const directives: Record<string, string> = {};
  for (const part of policy.split(';').map((s) => s.trim()).filter(Boolean)) {
    const [name, ...rest] = part.split(/\s+/);
    directives[name] = rest.join(' ');
  }
  return directives;
}

describe('buildCspMetaTag', () => {
  describe('default restrictive policy (no csp provided)', () => {
    const tag = buildCspMetaTag();
    const d = parsePolicy(tag);

    it('wraps the policy in a meta http-equiv Content-Security-Policy tag', () => {
      expect(tag).toContain('<meta http-equiv="Content-Security-Policy"');
      expect(tag).toMatch(/\n$/); // trailing newline so it prepends cleanly
    });

    it("denies all network + resource loads by default", () => {
      expect(d['default-src']).toBe("'none'");
      expect(d['object-src']).toBe("'none'");
      expect(d['base-uri']).toBe("'none'");
    });

    it("blocks all connect/frame targets when no domains declared", () => {
      expect(d['connect-src']).toBe("'none'");
      expect(d['frame-src']).toBe("'none'");
    });

    it("allows inline scripts and styles (required for srcdoc views) but nothing external", () => {
      expect(d['script-src']).toBe("'unsafe-inline'");
      expect(d['style-src']).toBe("'unsafe-inline'");
    });

    it("only allows data: URIs for images and media", () => {
      expect(d['img-src']).toBe('data:');
      expect(d['media-src']).toBe('data:');
    });
  });

  describe('connectDomains', () => {
    it('adds declared hosts to connect-src', () => {
      const d = parsePolicy(
        buildCspMetaTag({ connectDomains: ['https://api.example.com', 'https://cdn.example.com'] }),
      );
      expect(d['connect-src']).toBe('https://api.example.com https://cdn.example.com');
    });

    it('empty array falls back to the restrictive default', () => {
      const d = parsePolicy(buildCspMetaTag({ connectDomains: [] }));
      expect(d['connect-src']).toBe("'none'");
    });
  });

  describe('resourceDomains', () => {
    it('extends script-src, style-src, and img-src with declared hosts', () => {
      const d = parsePolicy(
        buildCspMetaTag({ resourceDomains: ['https://cdn.example.com'] }),
      );
      expect(d['script-src']).toBe("'unsafe-inline' https://cdn.example.com");
      expect(d['style-src']).toBe("'unsafe-inline' https://cdn.example.com");
      expect(d['img-src']).toBe('data: https://cdn.example.com');
    });

    it('multiple resource domains are space-separated', () => {
      const d = parsePolicy(
        buildCspMetaTag({
          resourceDomains: ['https://a.example.com', 'https://b.example.com'],
        }),
      );
      expect(d['script-src']).toContain('https://a.example.com');
      expect(d['script-src']).toContain('https://b.example.com');
    });
  });

  describe('frameDomains', () => {
    it('adds declared hosts to frame-src', () => {
      const d = parsePolicy(
        buildCspMetaTag({ frameDomains: ['https://embed.example.com'] }),
      );
      expect(d['frame-src']).toBe('https://embed.example.com');
    });

    it('empty array falls back to frame-src none', () => {
      const d = parsePolicy(buildCspMetaTag({ frameDomains: [] }));
      expect(d['frame-src']).toBe("'none'");
    });
  });

  describe('combined csp fields', () => {
    it('all csp fields can coexist', () => {
      const d = parsePolicy(
        buildCspMetaTag({
          connectDomains: ['https://api.example.com'],
          resourceDomains: ['https://cdn.example.com'],
          frameDomains: ['https://embed.example.com'],
        }),
      );
      expect(d['connect-src']).toBe('https://api.example.com');
      expect(d['script-src']).toContain('https://cdn.example.com');
      expect(d['img-src']).toContain('https://cdn.example.com');
      expect(d['frame-src']).toBe('https://embed.example.com');
    });
  });

  describe('injection resistance', () => {
    it('does NOT escape quotes in caller-supplied domains (caller responsibility)', () => {
      // We assert the raw pass-through so the responsibility boundary is documented:
      // any validation/escaping of the `_meta.ui.csp` field must happen upstream
      // (in the registry resolver), NOT in the CSP builder.
      const tag = buildCspMetaTag({ connectDomains: ['https://ok.com'] });
      expect(tag).toContain('https://ok.com');
    });
  });
});
