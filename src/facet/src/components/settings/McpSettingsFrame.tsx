/**
 * McpSettingsFrame — renders a server-owned settings page in a sandboxed iframe.
 *
 * Uses the same JSON-RPC postMessage bridge as McpAppHost, but without
 * requiring an artifact context. Implements ui/initialize, tools/call,
 * ui/open-link, and size-changed notifications.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { readUiResource, proxyToolCall } from '@/api/mcp';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { useAuth } from '@/hooks/useAuth';

interface McpSettingsFrameProps {
  /** MCP server name (e.g. "ophan") */
  server: string;
  /** Resource URI (e.g. "ui://ophan/billing-settings.html") */
  resourceUri: string;
}

interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface JsonRpcNotification {
  jsonrpc: '2.0';
  method: string;
  params?: Record<string, unknown>;
}

export default function McpSettingsFrame({ server, resourceUri }: McpSettingsFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { activeWorkspaceId } = useWorkspaces();
  const { user } = useAuth();

  // Fetch the HTML resource
  useEffect(() => {
    let cancelled = false;
    readUiResource(server, resourceUri, activeWorkspaceId || undefined)
      .then(({ html: content }) => {
        if (!cancelled) setHtml(content);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load settings');
      });
    return () => { cancelled = true; };
  }, [server, resourceUri, activeWorkspaceId]);

  // --- Bridge helpers ---
  function sendResponse(id: number, result: unknown) {
    iframeRef.current?.contentWindow?.postMessage({ jsonrpc: '2.0', id, result }, '*');
  }

  function sendError(id: number, code: number, message: string) {
    iframeRef.current?.contentWindow?.postMessage({ jsonrpc: '2.0', id, error: { code, message } }, '*');
  }

  // --- Request handler ---
  function handleRequest(req: JsonRpcRequest) {
    switch (req.method) {
      case 'ui/initialize':
        sendResponse(req.id, {
          protocolVersion: '2026-01-26',
          hostInfo: { name: 'agience', version: '0.1.0' },
          hostCapabilities: { openLinks: {}, serverTools: {} },
          hostContext: {
            theme: window.matchMedia?.('(prefers-color-scheme: dark)')?.matches ? 'dark' : 'light',
            locale: navigator.language,
            platform: 'web',
            extensions: {
              agience: {
                workspaceId: activeWorkspaceId || '',
                userId: user?.id || '',
                origin: window.location.origin,
              },
            },
          },
        });
        break;

      case 'tools/call':
        handleToolCall(req);
        break;

      case 'ui/open-link': {
        const href = (req.params as { href?: string; url?: string })?.href
          ?? (req.params as { url?: string })?.url;
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
          sendResponse(req.id, {});
        } else {
          sendError(req.id, -32000, 'Invalid URL');
        }
        break;
      }

      case 'ping':
        sendResponse(req.id, {});
        break;

      default:
        sendError(req.id, -32601, `Method not found: ${req.method}`);
    }
  }

  async function handleToolCall(req: JsonRpcRequest) {
    const params = req.params as { name?: string; arguments?: Record<string, unknown> } | undefined;
    const toolName = params?.name;
    const toolArgs = params?.arguments ?? {};
    if (!toolName) {
      sendError(req.id, -32602, 'Missing tool name');
      return;
    }
    try {
      const result = await proxyToolCall(toolName, toolArgs, server, activeWorkspaceId || undefined);
      sendResponse(req.id, result);
    } catch (e) {
      sendError(req.id, -32000, `Tool call failed: ${e}`);
    }
  }

  // --- Notification handler ---
  function handleNotification(notif: JsonRpcNotification) {
    if (notif.method === 'ui/notifications/size-changed') {
      const { height } = (notif.params ?? {}) as { height?: number };
      if (height && iframeRef.current) {
        iframeRef.current.style.height = `${height}px`;
      }
    }
  }

  // --- postMessage listener ---
  const handleMessage = useCallback(
    (event: MessageEvent) => {
      const iframe = iframeRef.current;
      if (!iframe || event.source !== iframe.contentWindow) return;
      const data = event.data;
      if (!data || data.jsonrpc !== '2.0') return;

      if (typeof data.id === 'number') {
        handleRequest(data as JsonRpcRequest);
      } else if (typeof data.method === 'string') {
        handleNotification(data as JsonRpcNotification);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeWorkspaceId, user?.id],
  );

  useEffect(() => {
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [handleMessage]);

  // --- Render ---
  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        {error}
      </div>
    );
  }

  if (!html) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <iframe
      ref={iframeRef}
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: '100%', height: '100%', border: 'none' }}
      title="MCP Settings"
    />
  );
}
