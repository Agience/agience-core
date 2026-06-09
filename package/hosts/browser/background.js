/**
 * Agience Browser Extension — Service Worker (background.js)
 *
 * Handles communication between content scripts and the Agience API.
 * Runs as a Manifest V3 service worker.
 */

const DEFAULT_BASE_URL = 'https://app.agience.ai';

/**
 * Load extension settings from chrome.storage.local.
 * Returns { apiKey, workspaceId, baseUrl }.
 */
async function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['apiKey', 'workspaceId', 'baseUrl'], (result) => {
      resolve({
        apiKey: result.apiKey || '',
        workspaceId: result.workspaceId || '',
        baseUrl: (result.baseUrl || DEFAULT_BASE_URL).replace(/\/$/, ''),
      });
    });
  });
}

/**
 * POST a new artifact to the user's Agience workspace.
 */
async function ingestArtifact({ title, content, sourceUrl, contentType = 'text/plain' }) {
  const { apiKey, workspaceId, baseUrl } = await getSettings();

  if (!apiKey) {
    return { ok: false, error: 'No API key configured. Open the Agience extension popup to set up.' };
  }
  if (!workspaceId) {
    return { ok: false, error: 'No workspace ID configured. Open the Agience extension popup to set up.' };
  }

  const context = JSON.stringify({
    content_type: contentType,
    title,
    source_url: sourceUrl,
    ingested_by: 'agience-browser-extension',
  });

  const response = await fetch(`${baseUrl}/workspaces/${workspaceId}/artifacts`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title, content, context }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    return { ok: false, error: `API error ${response.status}: ${text.slice(0, 200)}` };
  }

  const created = await response.json();
  return { ok: true, artifactId: created.id, title: created.title };
}

/**
 * Message handler — receives messages from content scripts.
 *
 * Supported message types:
 *   INGEST_TRANSCRIPT  { title, content, sourceUrl }  → ingest a transcript artifact
 */
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'INGEST_TRANSCRIPT') {
    ingestArtifact({
      title: message.title || 'Teams Transcript',
      content: message.content,
      sourceUrl: message.sourceUrl,
      contentType: 'text/plain',
    }).then(sendResponse);
    // Return true to keep the message channel open for async sendResponse
    return true;
  }
});
