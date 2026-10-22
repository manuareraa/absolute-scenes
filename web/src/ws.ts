// Client for the MatchHub Durable Object at /ws/match/:id. Overlays arrive ahead of time as
// `{type: "overlay", overlay}`; each is checked against the contract before it is used.
// If the hub cannot be reached, the app keeps playing the local fixture.
import { validate, type Overlay } from "@chalktalk/contracts";

export type SourceMode = "connecting" | "live" | "fixture";

export interface MatchSocketHandlers {
  onMode(mode: SourceMode, detail?: string): void;
  onOverlay(overlay: Overlay): void;
}

type WsCtor = new (url: string) => WebSocket;

export function matchWsUrl(matchId: string, loc: { protocol: string; host: string }): string {
  const scheme = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${loc.host}/ws/match/${encodeURIComponent(matchId)}`;
}

/** Parse one hub message; returns the overlay it carries, or null for other or bad messages. */
export function parseHubMessage(data: unknown): Overlay | null {
  if (typeof data !== "string") return null;
  let msg: unknown;
  try {
    msg = JSON.parse(data);
  } catch {
    return null;
  }
  if (!msg || typeof msg !== "object" || (msg as { type?: unknown }).type !== "overlay") return null;
  const overlay = (msg as { overlay?: unknown }).overlay;
  return validate("overlay", overlay).ok ? (overlay as Overlay) : null;
}

/**
 * Opens the hub socket. Falls back to fixture mode on error, on close, or if the socket has
 * not opened within `openTimeoutMs`. Returns a function that closes the socket.
 */
export function connectMatch(
  url: string,
  handlers: MatchSocketHandlers,
  opts: { openTimeoutMs?: number; WebSocketImpl?: WsCtor } = {},
): () => void {
  const Impl = opts.WebSocketImpl ?? (globalThis.WebSocket as WsCtor | undefined);
  if (!Impl) {
    handlers.onMode("fixture", "no WebSocket support");
    return () => {};
  }
  let done = false;
  const fallback = (why: string) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    handlers.onMode("fixture", why);
  };
  handlers.onMode("connecting");
  let ws: WebSocket;
  try {
    ws = new Impl(url);
  } catch {
    fallback("could not open socket");
    return () => {};
  }
  const timer = setTimeout(() => {
    fallback("hub timeout");
    ws.close();
  }, opts.openTimeoutMs ?? 3000);
  ws.onopen = () => {
    clearTimeout(timer);
    if (!done) handlers.onMode("live");
  };
  ws.onmessage = (ev: MessageEvent) => {
    const overlay = parseHubMessage(ev.data);
    if (overlay && !done) handlers.onOverlay(overlay);
  };
  ws.onerror = () => fallback("hub unavailable");
  ws.onclose = () => fallback("hub closed");
  return () => {
    done = true;
    clearTimeout(timer);
    ws.close();
  };
}
