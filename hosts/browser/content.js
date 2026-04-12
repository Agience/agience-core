/**
 * Agience Browser Extension — Content Script (content.js)
 *
 * Runs on https://teams.microsoft.com/* at document_start.
 *
 * Strategy: intercept fetch and XMLHttpRequest responses to detect the
 * Teams API call that returns a presigned URL to the meeting transcript.
 * When found, fetch the transcript and send it to the service worker for
 * ingestion into the user's Agience workspace.
 *
 * The Teams recap page loads transcript data via an authenticated API call.
 * The response JSON contains a field with a presigned HTTPS URL pointing to
 * the actual transcript file (.vtt, .docx, or similar). Because the URL is
 * presigned by Microsoft, no additional auth is required to download it.
 */

(function () {
  'use strict';

  // Guard: only inject once per page
  if (window.__agienceInjected) return;
  window.__agienceInjected = true;

  // Pattern: Teams transcript/recording API paths
  const TRANSCRIPT_PATH_PATTERN = /\/(transcripts|recordings|callRecords)/i;

  // Pattern: presigned download URL (Azure Blob Storage or similar CDN)
  const PRESIGNED_URL_PATTERN = /https:\/\/[^\s"']+(?:transcript|recording|caption)[^\s"']*\.(?:vtt|docx|txt|json)/i;

  let _captured = false;  // Only capture once per page load

  /**
   * Search a JSON body for a presigned transcript URL.
   * Returns the URL string if found, null otherwise.
   */
  function findTranscriptUrl(obj, depth = 0) {
    if (depth > 8 || !obj || typeof obj !== 'object') return null;
    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'string' && PRESIGNED_URL_PATTERN.test(value)) {
        return value;
      }
      if (typeof value === 'object') {
        const found = findTranscriptUrl(value, depth + 1);
        if (found) return found;
      }
    }
    return null;
  }

  /**
   * Download the transcript from a presigned URL and send to background.
   */
  async function captureTranscript(presignedUrl) {
    if (_captured) return;
    _captured = true;

    try {
      const resp = await fetch(presignedUrl);
      if (!resp.ok) {
        console.warn('[Agience] Failed to fetch transcript:', resp.status);
        return;
      }
      const content = await resp.text();
      const title = document.title || 'Teams Meeting Transcript';
      const sourceUrl = location.href;

      chrome.runtime.sendMessage(
        { type: 'INGEST_TRANSCRIPT', title, content, sourceUrl },
        (response) => {
          if (chrome.runtime.lastError) {
            console.warn('[Agience] Send failed:', chrome.runtime.lastError.message);
            return;
          }
          if (response && response.ok) {
            showToast('Transcript saved to Agience');
          } else {
            console.warn('[Agience] Ingest failed:', response && response.error);
            showToast('Agience: could not save transcript');
          }
        }
      );
    } catch (err) {
      console.warn('[Agience] Transcript capture error:', err);
    }
  }

  /**
   * Inspect a response body (text) from a Teams API call.
   */
  function inspectResponseBody(url, body) {
    if (_captured) return;
    if (!TRANSCRIPT_PATH_PATTERN.test(url)) return;
    try {
      const data = JSON.parse(body);
      const transcriptUrl = findTranscriptUrl(data);
      if (transcriptUrl) {
        console.log('[Agience] Found transcript URL:', transcriptUrl);
        captureTranscript(transcriptUrl);
      }
    } catch {
      // Not JSON — skip
    }
  }

  // --- Intercept fetch ---
  const _origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await _origFetch.apply(this, args);
    if (_captured) return response;

    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (TRANSCRIPT_PATH_PATTERN.test(url)) {
      // Clone so original response body is not consumed
      const clone = response.clone();
      clone.text().then((body) => inspectResponseBody(url, body)).catch(() => {});
    }
    return response;
  };

  // --- Intercept XMLHttpRequest ---
  const _origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__agienceUrl = url;
    return _origOpen.apply(this, [method, url, ...rest]);
  };

  const _origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    if (!_captured && this.__agienceUrl && TRANSCRIPT_PATH_PATTERN.test(this.__agienceUrl)) {
      this.addEventListener('load', () => {
        inspectResponseBody(this.__agienceUrl, this.responseText || '');
      });
    }
    return _origSend.apply(this, args);
  };

  // --- Toast notification ---
  function showToast(message) {
    const existing = document.getElementById('agience-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'agience-toast';
    toast.textContent = message;
    Object.assign(toast.style, {
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      padding: '10px 18px',
      background: '#6366f1',
      color: '#fff',
      borderRadius: '8px',
      fontFamily: 'system-ui, sans-serif',
      fontSize: '13px',
      fontWeight: '600',
      zIndex: '2147483647',
      boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      transition: 'opacity 0.4s',
      opacity: '1',
    });
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 500);
    }, 3000);
  }
})();
