// frontend/src/api/events.ts
//
// Unified real-time event subscription client for the /events WebSocket.
//
// Backed by the `WS /events` router endpoint. One connection can carry many
// filtered subscriptions. Auto-reconnects on disconnect and re-issues all
// active subscriptions.

import { getRuntimeConfig } from '../config/runtime';

/** Server-side filter applied before an event is delivered to a subscriber. */
export type EventFilter = {
  container_id?: string;
  artifact_id?: string;
  content_type?: string;
  /** fnmatch globs, e.g. ["artifact.invoke.*", "artifact.created"] */
  event_names?: string[];
};

/** A single event message delivered from the server. */
export type BusEvent = {
  event: string;
  payload: Record<string, unknown>;
  sub_id: string;
  ts: number;
  event_id: string;
};

export type EventHandler = (event: BusEvent) => void;

type PendingSub = {
  clientId: string;
  filter: EventFilter;
  handler: EventHandler;
  acked: boolean;
};

type ConnectionState = 'idle' | 'connecting' | 'open' | 'closing';

function buildWsUrl(): string {
  const http = (getRuntimeConfig().backendUri || 'http://localhost:8081').replace(/\/$/, '');
  const wsBase = http.replace(/^http/, 'ws');
  return `${wsBase}/events`;
}

/**
 * Open (or reuse) a shared /events WebSocket and subscribe with a filter.
 *
 * Returns an `unsubscribe` function. Safe to call from React effects — call
 * the returned function in the cleanup to stop receiving events.
 *
 * ```tsx
 * useEffect(() => subscribeEvents(
 *   { container_id: workspaceId, event_names: ["artifact.*"] },
 *   (evt) => { ... }
 * ), [workspaceId]);
 * ```
 */
export function subscribeEvents(
  filter: EventFilter,
  handler: EventHandler,
): () => void {
  return eventsClient.subscribe(filter, handler);
}

class EventsClient {
  private ws: WebSocket | null = null;
  private state: ConnectionState = 'idle';
  private subs: Map<string, PendingSub> = new Map();
  private nextSubId = 1;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  subscribe(filter: EventFilter, handler: EventHandler): () => void {
    const clientId = `sub-${this.nextSubId++}`;
    const sub: PendingSub = { clientId, filter, handler, acked: false };
    this.subs.set(clientId, sub);

    if (this.state === 'idle') {
      this.connect();
    } else if (this.state === 'open' && this.ws) {
      this.sendSubscribe(sub);
    }

    return () => {
      const existing = this.subs.get(clientId);
      if (!existing) return;
      this.subs.delete(clientId);
      if (this.state === 'open' && this.ws) {
        try {
          this.ws.send(JSON.stringify({ op: 'unsubscribe', id: clientId }));
        } catch { /* ignore */ }
      }
      // If no subscriptions remain, close the connection.
      if (this.subs.size === 0 && this.ws) {
        this.state = 'closing';
        try { this.ws.close(); } catch { /* ignore */ }
      }
    };
  }

  private connect(): void {
    if (this.state === 'connecting' || this.state === 'open') return;
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') return;

    this.state = 'connecting';
    const token = localStorage.getItem('access_token') || '';
    // Browsers can't set Authorization headers on WebSocket — pass via query param.
    // The server accepts either header or ?access_token=.
    const url = `${buildWsUrl()}?access_token=${encodeURIComponent(token)}`;

    try {
      this.ws = new WebSocket(url);
    } catch {
      this.state = 'idle';
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.state = 'open';
      this.reconnectAttempt = 0;
      // Re-issue every active subscription.
      for (const sub of this.subs.values()) {
        sub.acked = false;
        this.sendSubscribe(sub);
      }
    };

    this.ws.onmessage = (ev) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(ev.data);
      } catch { return; }
      if (!parsed || typeof parsed !== 'object') return;
      const msg = parsed as Record<string, unknown>;

      if (typeof msg.ack === 'string') {
        const sub = this.subs.get(msg.ack);
        if (sub) sub.acked = true;
        return;
      }
      if (typeof msg.unack === 'string' || msg.pong === true) return;
      if (typeof msg.event === 'string' && typeof msg.sub_id === 'string') {
        const sub = this.subs.get(msg.sub_id);
        if (sub) {
          try {
            sub.handler(msg as unknown as BusEvent);
          } catch (err) {
            // Don't let a handler exception kill the socket.
            console.warn('events handler threw:', err);
          }
        }
      }
    };

    this.ws.onclose = () => {
      const wasOpen = this.state === 'open';
      this.ws = null;
      this.state = 'idle';
      if (this.subs.size > 0 && wasOpen) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // Let onclose handle reconnection.
    };
  }

  private sendSubscribe(sub: PendingSub): void {
    if (!this.ws || this.state !== 'open') return;
    try {
      this.ws.send(JSON.stringify({
        op: 'subscribe',
        id: sub.clientId,
        filter: sub.filter,
      }));
    } catch { /* reconnect will re-send */ }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(30_000, 500 * Math.pow(2, this.reconnectAttempt));
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.subs.size > 0) this.connect();
    }, delay);
  }
}

const eventsClient = new EventsClient();
