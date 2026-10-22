// Live playback from the MatchHub clock (workers/edge, docs/notes/d-edge.md). The hub sends
// `frames` batches ahead of its clock and `{t, playing, rate, server_ms}` clock stamps; the web
// anchors each stamp to its own monotonic clock on receipt and plays the buffered frames.
// Plain data and pure functions, so it unit-tests without a socket.
import type { Frame, Overlay } from "@chalktalk/contracts";
import { breakdownDurationMs, frameAt } from "./playback";

export interface HubClock {
  t: number;
  playing: boolean;
  rate: number;
  server_ms: number;
}

export type HubMessage =
  | { type: "hello"; match_id: string; fps: number; duration_ms: number; batch_ms: number; viewers: number; clock: HubClock }
  | { type: "frames"; t0: number; t1: number; clock: HubClock; frames: Frame[]; events: unknown[] }
  | { type: "overlay"; overlay: Overlay }
  | { type: "clock"; clock: HubClock }
  | { type: "end"; clock: HubClock };

/** Frames older than this behind the clock are dropped from the buffer. */
export const KEEP_BEHIND_MS = 15_000;

export interface LiveState {
  /** Match ms at local time `anchorLocal`. */
  anchorT: number;
  anchorLocal: number;
  playing: boolean;
  rate: number;
  durationMs: number;
  ended: boolean;
  frames: Frame[];
}

export function newLiveState(): LiveState {
  return { anchorT: 0, anchorLocal: 0, playing: false, rate: 1, durationMs: 0, ended: false, frames: [] };
}

/** Match ms now, on the hub's clock as anchored locally. */
export function liveMatchT(s: LiveState, nowLocal: number): number {
  if (!s.playing) return s.anchorT;
  const t = s.anchorT + (nowLocal - s.anchorLocal) * s.rate;
  return Math.max(0, s.durationMs ? Math.min(s.durationMs, t) : t);
}

function anchor(s: LiveState, c: HubClock, nowLocal: number): LiveState {
  return { ...s, anchorT: c.t, anchorLocal: nowLocal, playing: c.playing, rate: c.rate };
}

/** Merge new frames (sorted by t, no duplicates) and trim the old ones. */
export function mergeFrames(buf: Frame[], incoming: Frame[], nowT: number): Frame[] {
  const byT = new Map<number, Frame>();
  for (const f of buf) if (f.t >= nowT - KEEP_BEHIND_MS) byT.set(f.t, f);
  for (const f of incoming) byT.set(f.t, f);
  return [...byT.values()].sort((a, b) => a.t - b.t);
}

/** Apply one hub message received at local time `nowLocal`. Overlays are handled by the caller. */
export function applyHubMessage(s: LiveState, msg: HubMessage, nowLocal: number): LiveState {
  switch (msg.type) {
    case "hello":
      return { ...anchor(s, msg.clock, nowLocal), durationMs: msg.duration_ms, ended: false };
    case "frames": {
      const next = anchor(s, msg.clock, nowLocal);
      return { ...next, frames: mergeFrames(s.frames, msg.frames, msg.clock.t) };
    }
    case "clock":
      // A seek can jump anywhere; keep only frames near the new time.
      return { ...anchor(s, msg.clock, nowLocal), frames: s.frames.filter((f) => Math.abs(f.t - msg.clock.t) < KEEP_BEHIND_MS), ended: false };
    case "end":
      return { ...anchor(s, msg.clock, nowLocal), ended: true };
    case "overlay":
      return s;
  }
}

/** The frame to show at live time `t`; undefined until the first batch lands. */
export function liveFrame(s: LiveState, t: number): Frame | undefined {
  if (!s.frames.length || t < s.frames[0].t - 1000) return undefined;
  return frameAt(s.frames, t);
}

/**
 * Fires breakdowns on the live clock: when live time crosses an overlay's `match_tc`, the
 * picture holds on that moment while the script plays, then rejoins live. An overlay that
 * arrives more than `lateMs` after its moment is not played (it missed its stoppage).
 */
export class LiveDirector {
  private fired = new Set<string>();
  private active: { overlay: Overlay; startLocal: number; dur: number } | null = null;
  private lastT = -1;

  constructor(private lateMs = 8000) {}

  step(overlays: Overlay[], t: number, nowLocal: number): { overlay: Overlay | null; audioMs: number } {
    if (this.active && nowLocal - this.active.startLocal >= this.active.dur) this.active = null;
    // A backwards seek re-arms the moments after the new time.
    if (t < this.lastT - 1000) for (const o of overlays) if (o.match_tc > t) this.fired.delete(o.id);
    this.lastT = t;
    if (!this.active) {
      const due = overlays
        .filter((o) => !this.fired.has(o.id) && o.match_tc <= t)
        .sort((a, b) => b.match_tc - a.match_tc);
      for (const o of due) this.fired.add(o.id);
      const next = due.find((o) => t - o.match_tc <= this.lateMs);
      if (next) this.active = { overlay: next, startLocal: nowLocal, dur: breakdownDurationMs(next) };
    }
    return this.active ? { overlay: this.active.overlay, audioMs: nowLocal - this.active.startLocal } : { overlay: null, audioMs: 0 };
  }
}
