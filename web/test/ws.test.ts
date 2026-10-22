import { afterEach, describe, expect, it, vi } from "vitest";
import { makeFixture } from "../src/fixture/synthetic";
import { connectMatch, matchWsUrl, parseHubMessage, type SourceMode } from "../src/ws";

class FakeSocket {
  static last: FakeSocket;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  close() {
    this.closed = true;
  }
}
const Impl = FakeSocket as unknown as new (url: string) => WebSocket;
const overlay = makeFixture().overlays[0];

function setup(timeout = 3000) {
  const modes: SourceMode[] = [];
  const got: string[] = [];
  const stop = connectMatch("ws://x/ws/match/demo-001", { onMode: (m) => modes.push(m), onMessage: (m) => got.push(m.type === "overlay" ? m.overlay.id : m.type) }, { WebSocketImpl: Impl, openTimeoutMs: timeout });
  return { modes, got, stop, sock: FakeSocket.last };
}

afterEach(() => vi.useRealTimers());

describe("match socket", () => {
  it("builds ws and wss URLs", () => {
    expect(matchWsUrl("demo-001", { protocol: "http:", host: "localhost:5173" })).toBe("ws://localhost:5173/ws/match/demo-001");
    expect(matchWsUrl("m 1", { protocol: "https:", host: "a.b" })).toBe("wss://a.b/ws/match/m%201");
  });

  it("parses hub messages and rejects malformed ones", () => {
    const clock = { t: 1000, playing: true, rate: 1, server_ms: 5 };
    const o = parseHubMessage(JSON.stringify({ type: "overlay", overlay }));
    expect(o?.type === "overlay" && o.overlay.id).toBe(overlay.id);
    expect(parseHubMessage(JSON.stringify({ type: "hello", viewers: 1, match_id: "m", fps: 25, duration_ms: 9, batch_ms: 1000, clock }))?.type).toBe("hello");
    expect(parseHubMessage(JSON.stringify({ type: "frames", t0: 0, t1: 1000, clock, frames: [], events: [] }))?.type).toBe("frames");
    expect(parseHubMessage(JSON.stringify({ type: "clock", clock }))?.type).toBe("clock");
    expect(parseHubMessage(JSON.stringify({ type: "end", clock }))?.type).toBe("end");
    expect(parseHubMessage(JSON.stringify({ type: "hello", viewers: 1 }))).toBeNull();
    expect(parseHubMessage(JSON.stringify({ type: "clock", clock: { t: "x" } }))).toBeNull();
    expect(parseHubMessage(JSON.stringify({ type: "pong" }))).toBeNull();
    expect(parseHubMessage(JSON.stringify({ type: "overlay", overlay: { id: "x" } }))).toBeNull();
    expect(parseHubMessage("not json")).toBeNull();
    expect(parseHubMessage(new ArrayBuffer(2))).toBeNull();
  });

  it("goes live on open and passes overlays through", () => {
    const { modes, got, sock } = setup();
    sock.onopen!();
    sock.onmessage!({ data: JSON.stringify({ type: "overlay", overlay }) });
    expect(modes).toEqual(["connecting", "live"]);
    expect(got).toEqual([overlay.id]);
  });

  it("falls back to fixture playback on error or close", () => {
    const { modes, sock } = setup();
    sock.onerror!();
    sock.onclose!();
    expect(modes).toEqual(["connecting", "fixture"]);
  });

  it("falls back when the hub does not open in time", () => {
    vi.useFakeTimers();
    const { modes, sock } = setup(1000);
    vi.advanceTimersByTime(1001);
    expect(modes).toEqual(["connecting", "fixture"]);
    expect(sock.closed).toBe(true);
  });
});
