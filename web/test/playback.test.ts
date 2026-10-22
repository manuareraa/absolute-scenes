import { describe, expect, it } from "vitest";
import { strokeStartMs, type Overlay } from "@chalktalk/contracts";
import { makeFixture } from "../src/fixture/synthetic";
import { TAIL_MS, breakdownDurationMs, frameAt, playStateAt, selectOverlays, strokeProgress, timeline, wordIndexAt } from "../src/playback";

const fx = makeFixture();
const end = fx.frames[fx.frames.length - 1].t;
const casual = selectOverlays(fx.overlays, "broadcast", "casual");

describe("frameAt", () => {
  it("returns the latest frame at or before t", () => {
    expect(frameAt(fx.frames, 0)?.t).toBe(0);
    expect(frameAt(fx.frames, 59)?.t).toBe(40);
    expect(frameAt(fx.frames, 80)?.t).toBe(80);
    expect(frameAt(fx.frames, 1e9)?.t).toBe(end);
    expect(frameAt([], 10)).toBeUndefined();
  });
});

describe("stroke timing", () => {
  const ov = casual[0];
  const s = ov.strokes[0];
  const start = strokeStartMs(ov.script.cues, s);

  it("starts each stroke lead_ms before its cue word", () => {
    const cue = ov.script.cues.find((c) => c.cue_id === s.cue_id)!;
    expect(start).toBe(cue.offset_ms - (s.lead_ms ?? 150));
  });

  it("draws on from 0 to 1 over duration_ms", () => {
    expect(strokeProgress(ov, s, start - 1)).toBeNull();
    expect(strokeProgress(ov, s, start)).toBe(0);
    expect(strokeProgress(ov, s, start + (s.duration_ms ?? 600) / 2)).toBeCloseTo(0.5);
    expect(strokeProgress(ov, s, start + 10_000)).toBe(1);
  });

  it("holds the frame until words and strokes end, plus a tail", () => {
    const words = ov.script.words!;
    const lastWord = words[words.length - 1];
    expect(breakdownDurationMs(ov)).toBeGreaterThanOrEqual(lastWord.offset_ms + lastWord.duration_ms + TAIL_MS);
  });

  it("tracks the word being spoken", () => {
    const w = ov.script.words!;
    expect(wordIndexAt(ov, 0)).toBe(-1);
    expect(wordIndexAt(ov, w[2].offset_ms + 1)).toBe(2);
  });
});

describe("playStateAt", () => {
  const [m1, m2] = [...casual].sort((a, b) => a.match_tc - b.match_tc);
  const d1 = breakdownDurationMs(m1);

  it("plays the match until the first moment", () => {
    expect(playStateAt(1000, end, casual)).toEqual({ matchT: 1000, overlay: null, audioMs: 0 });
  });

  it("freezes on the moment while its script plays", () => {
    const st = playStateAt(m1.match_tc + 500, end, casual);
    expect(st.overlay?.id).toBe(m1.id);
    expect(st.matchT).toBe(m1.match_tc);
    expect(st.audioMs).toBe(500);
  });

  it("resumes after the breakdown and reaches the second moment", () => {
    expect(playStateAt(m1.match_tc + d1 + 100, end, casual)).toMatchObject({ matchT: m1.match_tc + 100, overlay: null });
    expect(playStateAt(m2.match_tc + d1, end, casual).overlay?.id).toBe(m2.id);
  });

  it("loops, and agrees with timeline()", () => {
    const tl = timeline(end, casual);
    expect(tl.starts.map((s) => s.at)).toEqual([m1.match_tc, m2.match_tc + d1]);
    expect(playStateAt(tl.loopMs + 1000, end, casual).matchT).toBe(1000);
  });

  it("plays straight through with no overlays", () => {
    expect(playStateAt(5000, end, []).matchT).toBe(5000);
  });
});

describe("selectOverlays", () => {
  it("picks one overlay per moment for the surface and lens", () => {
    const sel = selectOverlays(fx.overlays, "show", "analyst");
    expect(sel).toHaveLength(2);
    expect(sel.every((o) => o.surface === "show" && o.lens === "analyst")).toBe(true);
  });

  it("falls back to another surface and skips pending or rejected overlays", () => {
    const only = fx.overlays.filter((o) => o.surface === "broadcast" && o.lens === "casual");
    expect(selectOverlays(only, "player", "casual").map((o) => o.surface)).toEqual(["broadcast", "broadcast"]);
    const pending: Overlay[] = only.map((o) => ({ ...o, approval: { state: "pending" } }));
    expect(selectOverlays(pending, "broadcast", "casual")).toEqual([]);
  });
});
