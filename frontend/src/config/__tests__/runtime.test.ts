import { beforeEach, describe, expect, it } from 'vitest';

import { applyDocumentConfig, getRuntimeConfig } from '../runtime';

const expectedTitle = import.meta.env.VITE_TITLE || 'Agience';
const expectedFavicon = import.meta.env.VITE_FAVICON || '/favicon.png';

describe('runtime config branding', () => {
  beforeEach(() => {
    delete (window as { __AGIENCE_CONFIG__?: unknown }).__AGIENCE_CONFIG__;
    document.title = '';
    document.querySelectorAll('link[data-agience-favicon="true"]').forEach((node) => node.remove());
  });

  it('uses local defaults for title and favicon when no runtime config is present', () => {
    const cfg = getRuntimeConfig();

    expect(cfg.title).toBe(expectedTitle);
    expect(cfg.favicon).toBe(expectedFavicon);
  });

  it('applies document title and creates favicon link from defaults', () => {
    applyDocumentConfig();

    expect(document.title).toBe(expectedTitle);
    const favicon = document.querySelector<HTMLLinkElement>('link[data-agience-favicon="true"]');
    expect(favicon).toBeTruthy();
    expect(favicon?.getAttribute('href')).toBe(expectedFavicon);
  });

  it('applies runtime override for title and favicon', () => {
    (window as { __AGIENCE_CONFIG__?: unknown }).__AGIENCE_CONFIG__ = {
      title: 'Custom Local',
      favicon: '/custom-favicon.png',
      backendUri: 'http://localhost:8081',
      clientId: 'local-client',
    };

    applyDocumentConfig();

    expect(document.title).toBe('Custom Local');
    const favicon = document.querySelector<HTMLLinkElement>('link[data-agience-favicon="true"]');
    expect(favicon?.getAttribute('href')).toBe('/custom-favicon.png');
  });
});
