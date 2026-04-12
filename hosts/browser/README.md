# Agience Browser Extension

Status: **Draft**
Date: 2026-04-01

Chrome Extension (Manifest V3) that ingests content from browser tabs into an Agience workspace.

---

## Installing (development)

1. Open `chrome://extensions` in Chrome or Edge.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select this `hosts/browser/` directory.
4. Click the Agience extension icon → enter your Agience URL, API key, and workspace ID.

---

## Configuration

| Field | Description |
|-------|-------------|
| **Agience URL** | Base URL of your Agience instance (default: `https://app.agience.ai`) |
| **API Key** | Create via Agience UI → Settings → API Keys. Needs `workspaces:write` scope. |
| **Workspace ID** | UUID of the workspace where captured content should land. |

---

## Teams transcript ingestion

When you open a Teams meeting recap page (`teams.microsoft.com`), the extension automatically intercepts the API call that loads the transcript. When a presigned transcript URL is detected in the response:

1. The transcript file (`.vtt` or `.docx`) is downloaded from the presigned URL (no auth required — Microsoft pre-signs it).
2. A new artifact is created in your Agience workspace with `content_type: text/plain`.
3. A toast notification confirms the capture.

The transcript is captured once per page load. No data is sent until a transcript URL is detected.

---

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | MV3 extension manifest |
| `background.js` | Service worker — Agience API calls |
| `content.js` | Content script — Teams response interception |
| `popup.html` / `popup.js` | Settings popup |
| `icons/` | Extension icons (add 16×16, 48×48, 128×128 PNG files) |

---

## Packaging for distribution

Chrome Web Store requires a ZIP of this directory:

```bash
cd hosts/browser
zip -r agience-extension.zip . --exclude "*.md" --exclude ".git*"
```

Submit via the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole).
