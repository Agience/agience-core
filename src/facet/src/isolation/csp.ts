/**
 * CSP builder for MCP Apps iframe sandbox.
 *
 * Constructs a Content-Security-Policy <meta> tag from `_meta.ui.csp` metadata.
 * Per MCP Apps spec, the default CSP is restrictive — only declared domains
 * are added.
 *
 * Spec reference: SEP-1865 Section 9 — Default CSP.
 */

import type { CspDomains } from './McpAppHost';

/**
 * Build a CSP meta tag string to inject into the iframe's srcdoc.
 *
 * Returns an empty string if no CSP override is needed (the browser's default
 * iframe sandbox restrictions apply).
 */
export function buildCspMetaTag(csp?: CspDomains): string {
  const directives: string[] = [
    "default-src 'none'",
    "script-src 'unsafe-inline'",
    "style-src 'unsafe-inline'",
    "img-src data:",
    "media-src data:",
    "object-src 'none'",
    "base-uri 'none'",
  ];

  if (csp?.connectDomains?.length) {
    directives.push(`connect-src ${csp.connectDomains.join(' ')}`);
  } else {
    directives.push("connect-src 'none'");
  }

  if (csp?.resourceDomains?.length) {
    const domains = csp.resourceDomains.join(' ');
    // Update script-src and style-src to include declared domains
    directives[1] = `script-src 'unsafe-inline' ${domains}`;
    directives[2] = `style-src 'unsafe-inline' ${domains}`;
    directives[3] = `img-src data: ${domains}`;
  }

  if (csp?.frameDomains?.length) {
    directives.push(`frame-src ${csp.frameDomains.join(' ')}`);
  } else {
    directives.push("frame-src 'none'");
  }

  const policy = directives.join('; ');
  return `<meta http-equiv="Content-Security-Policy" content="${policy}">\n`;
}
