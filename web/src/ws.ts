// Client for the MatchHub Durable Object at /ws/match/:id (protocol: docs/notes/d-edge.md).
// The hub sends `hello`, `frames`, `clock`, `end` and `overlay`; overlays are checked against
// the contract before they are used. If the hub cannot be reached, the app plays the fixture.
import { validate } from "@chalktalk/contracts";
import type { HubClock, HubMessage } from "./live";

export type SourceMode = "connecting" | "live" | "fixture";

export interface MatchSocketHandlers {
  onMode(mode: SourceMode, detail?: string): void;
  onMessage(msg: HubMessage): void;
}

type WsCtor = new (url: string) => WebSocket;

export function matchWsUrl(matchId: string, loc: { protocol: string; host: string }): string {
  const scheme = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${loc.host}/ws/match/${encodeURIComponent(matchId)}`;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function isClock(c: unknown): c is HubClock {
  const k = c as Partial<HubClock> | null;
  return !!k && isNum(k.t) && typeof k.playing === "boolean" && isNum(k.rate) && isNum(k.server_ms);
}

/** Parse one hub message; returns null for unknown or malformed messages. */
export function parseHubMessage(data: unknown): HubMessage | null {
  if (typeof data !== "string") return null;
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(data);
  } catch {
    return null;
  }
  if (!msg || typeof msg !== "object") return null;
  switch (msg.type) {
    case "overlay":
      return validate("overlay", msg.overlay).ok ? (msg as unknown as HubMessage) : null;
    case "hello":
      return isClock(msg.clock) && isNum(msg.duration_ms) ? (msg as unknown as HubMessage) : null;
    case "frames":
      return isClock(msg.clock) && Array.isArray(msg.frames) ? (msg as unknown as HubMessage) : null;
    case "clock":
    case "end":
      return isClock(msg.clock) ? (msg as unknown as HubMessage) : null;
    default:
      return null;
  }
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
    const msg = parseHubMessage(ev.data);
    if (msg && !done) handlers.onMessage(msg);
  };
  ws.onerror = () => fallback("hub unavailable");
  ws.onclose = () => fallback("hub closed");
  return () => {
    done = true;
    clearTimeout(timer);
    ws.close();
  };
}

/** Back-off between reconnects after a live hub drops; the last delay repeats. */
export const RECONNECT_MS = [2000, 5000, 10_000, 30_000];
const MAX_RECONNECTS = 12;

/**
 * `connectMatch` that reconnects after a live hub drops (a Worker deploy or a Durable Object
 * restart), with a back-off and a cap. A hub that never opened falls back to the fixture as before.
 */
export function keepConnected(
  url: string,
  handlers: MatchSocketHandlers,
  opts: { openTimeoutMs?: number; WebSocketImpl?: WsCtor } = {},
): () => void {
  let wasLive = false;
  let tries = 0;
  let stopped = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let close = () => {};
  const open = () => {
    close = connectMatch(
      url,
      {
        onMessage: handlers.onMessage,
        onMode: (mode, detail) => {
          if (mode === "live") [wasLive, tries] = [true, 0];
          if (mode !== "fixture" || !wasLive || stopped || tries >= MAX_RECONNECTS) {
            if (mode !== "connecting" || !wasLive) handlers.onMode(mode, detail);
            return;
          }
          handlers.onMode("connecting", `reconnecting (${detail ?? "hub closed"})`);
          retry = setTimeout(open, RECONNECT_MS[Math.min(tries++, RECONNECT_MS.length - 1)]);
        },
      },
      opts,
    );
  };
  open();
  return () => {
    stopped = true;
    clearTimeout(retry);
    close();
  };
}
