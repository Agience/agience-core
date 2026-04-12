/**
 * Agience Browser Extension — Popup script (popup.js)
 */

const DEFAULT_BASE_URL = 'https://app.agience.ai';

function $(id) { return document.getElementById(id); }

/** Load saved settings into form fields */
function loadSettings() {
  chrome.storage.local.get(['apiKey', 'workspaceId', 'baseUrl', 'lastCapture'], (result) => {
    $('baseUrl').value = result.baseUrl || DEFAULT_BASE_URL;
    $('apiKey').value = result.apiKey || '';
    $('workspaceId').value = result.workspaceId || '';

    if (result.lastCapture) {
      $('lastCapture').textContent = result.lastCapture;
      $('lastCapture').classList.remove('empty');
    }
  });
}

/** Save form fields to chrome.storage.local */
function saveSettings() {
  const settings = {
    baseUrl: $('baseUrl').value.trim().replace(/\/$/, '') || DEFAULT_BASE_URL,
    apiKey: $('apiKey').value.trim(),
    workspaceId: $('workspaceId').value.trim(),
  };
  chrome.storage.local.set(settings, () => {
    const msg = $('toastMsg');
    msg.style.display = 'block';
    setTimeout(() => { msg.style.display = 'none'; }, 2000);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  $('saveBtn').addEventListener('click', saveSettings);
});
