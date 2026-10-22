import { describe, expect, it } from "vitest";
import type { Frame } from "@chalktalk/contracts";
import { makeFixture } from "../src/fixture/synthetic";
import { applyHubMessage, KEEP_BEHIND_MS, liveFrame, LiveDirector, liveMatchT, newLiveState, type HubClock } from "../src/live";
import { breakdownDurationMs } from "../src/playback";

const fx = makeFixture();
const clock = (t: number, playing = true, rate = 1): HubClock => ({ t, playing, rate, server_ms: 0 });
const hello = (c: HubClock) => ({ type: "hello" as const, match_id: "m", fps: 25, duration_ms: 12_000, batch_ms: 1000, viewers: 1, clock: c });
const batch = (t0: number, t1: number, c: HubClock) => ({
  type: "frames" as const,
  t0,
  t1,
  clock: c,
  frames: fx.frames.filter((f) => f.t >= t0 && f.t < t1),
  events: [],
});

describe("live clock", () => {
  it("anchors the hub clock on receipt and advances at its rate", () => {
    const s = applyHubMessage(newLiveState(), hello(clock(2000, true, 2)), 100);
    expect(liveMatchT(s, 100)).toBe(2000);
    expect(liveMatchT(s, 600)).toBe(3000);
    expect(liveMatchT(s, 1e9)).toBe(12_000); // clamped to the match length
  });

  it("holds still when paused", () => {
    const s = applyHubMessage(newLiveState(), { type: "clock", clock: clock(4000, false) }, 0);
    expect(liveMatchT(s, 5000)).toBe(4000);
  });

  it("buffers frame batches, re-anchors on each, and shows the frame at live time", () => {
    let s = applyHubMessage(newLiveState(), hello(clock(0)), 0);
    expect(liveFrame(s, 0)).toBeUndefined();
    s = applyHubMessage(s, batch(0, 1000, clock(0)), 0);
    s = applyHubMessage(s, batch(1000, 2000, clock(1040)), 1000); // hub 40 ms ahead
    expect(s.frames.length).toBe(50);
    expect(liveMatchT(s, 1000)).toBe(1040);
    expect(liveFrame(s, liveMatchT(s, 1500))?.t).toBe(1520);
  });

  it("drops duplicate frames and trims the old ones", () => {
    let s = newLiveState();
    s = applyHubMessage(s, batch(0, 1000, clock(0)), 0);
    s = applyHubMessage(s, batch(0, 1000, clock(0)), 0);
    expect(s.frames.length).toBe(25);
    const late: Frame[] = fx.frames.slice(0, 1).map((f) => ({ ...f, t: KEEP_BEHIND_MS + 5000 }));
    s = applyHubMessage(s, { type: "frames", t0: 0, t1: 0, clock: clock(KEEP_BEHIND_MS + 5000), frames: late, events: [] }, 0);
    expect(s.frames.map((f) => f.t)).toEqual([KEEP_BEHIND_MS + 5000]);
  });

  it("marks the end", () => {
    const s = applyHubMessage(newLiveState(), { type: "end", clock: clock(12_000, false) }, 0);
    expect(s.ended).toBe(true);
    expect(liveMatchT(s, 99)).toBe(12_000);
  });
});

describe("live director", () => {
  const o = fx.overlays.find((x) => x.surface === "broadcast" && x.lens === "casual")!;

  it("holds on a moment when live time crosses it, then rejoins live", () => {
    const d = new LiveDirector();
    expect(d.step([o], o.match_tc - 40, 0).overlay).toBeNull();
    const hit = d.step([o], o.match_tc + 10, 100);
    expect(hit.overlay?.id).toBe(o.id);
    expect(d.step([o], o.match_tc + 500, 600).audioMs).toBe(500);
    const dur = breakdownDurationMs(o);
    expect(d.step([o], o.match_tc + 500, 100 + dur).overlay).toBeNull();
    expect(d.step([o], o.match_tc + 600, 200 + dur).overlay).toBeNull(); // fires once
  });

  it("skips an overlay that arrives too late for its moment", () => {
    const d = new LiveDirector(5000);
    expect(d.step([o], o.match_tc + 6000, 0).overlay).toBeNull();
  });

  it("re-arms moments after a backwards seek", () => {
    const d = new LiveDirector();
    d.step([o], o.match_tc + 1, 0);
    const dur = breakdownDurationMs(o);
    d.step([o], o.match_tc + 1, dur + 1);
    d.step([o], 0, dur + 2);
    expect(d.step([o], o.match_tc + 1, dur + 3).overlay?.id).toBe(o.id);
  });
});
