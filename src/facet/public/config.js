// Local-dev default for window.__AGIENCE_CONFIG__. In a container this file is
// OVERWRITTEN at startup by /docker-entrypoint.d/40-runtime-config.sh
// (package/docker/facet-runtime-config.sh) from runtime env. Keys must match
// src/facet/src/config/runtime.ts.
window.__AGIENCE_CONFIG__ = window.__AGIENCE_CONFIG__ || Object.freeze({
  originUri: 'http://localhost:8080',
  mantleUri: 'http://localhost:8081',
  clientId: 'platform',
  title: 'Agience',
  favicon: '/favicon.png',
});
