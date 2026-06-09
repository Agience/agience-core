type RuntimeConfig = {
  mantleUri: string;
  originUri: string;
  clientId: string;
  title: string;
  favicon: string;
};

const DEFAULT_CONFIG: RuntimeConfig = {
  mantleUri:
    import.meta.env.VITE_MANTLE_URI ||
    'http://localhost:8081',
  originUri: import.meta.env.VITE_ORIGIN_URI || 'http://localhost:8080',
  clientId: import.meta.env.VITE_CLIENT_ID || '',
  title: import.meta.env.VITE_TITLE || 'Agience',
  favicon: import.meta.env.VITE_FAVICON || '/favicon.png',
};

function normalizeString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

export function getRuntimeConfig(): RuntimeConfig {
  const runtimeConfig = window.__AGIENCE_CONFIG__;

  if (!runtimeConfig) {
    return DEFAULT_CONFIG;
  }

  return {
    mantleUri: normalizeString(
      runtimeConfig.mantleUri ?? runtimeConfig.backendUri,
      DEFAULT_CONFIG.mantleUri,
    ),
    originUri: normalizeString(runtimeConfig.originUri, DEFAULT_CONFIG.originUri),
    clientId: normalizeString(runtimeConfig.clientId, DEFAULT_CONFIG.clientId),
    title: normalizeString(runtimeConfig.title, DEFAULT_CONFIG.title),
    favicon: normalizeString(runtimeConfig.favicon, DEFAULT_CONFIG.favicon),
  };
}

export function applyDocumentConfig(): void {
  const config = getRuntimeConfig();
  document.title = config.title;

  let favicon = document.querySelector<HTMLLinkElement>('link[data-agience-favicon]');
  if (!favicon) {
    favicon = document.createElement('link');
    favicon.rel = 'icon';
    favicon.setAttribute('data-agience-favicon', 'true');
    document.head.appendChild(favicon);
  }

  favicon.href = config.favicon;
}