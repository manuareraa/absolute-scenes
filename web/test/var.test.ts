import { describe, expect, it } from "vitest";
import { validate } from "@chalktalk/contracts";
import raw from "../public/fixtures/show-sim-7.json?raw";
import type { ShowFixture } from "../src/show";
import { decidingMoments } from "../src/summary";
import { evidenceFor, frameBetween, geometryOverlay } from "../src/evidence";
import { isProvisional, varBanner, varFor, varGraphics } from "../src/var";

const fx: ShowFixture = JSON.parse(raw);
const varChapters = fx.shows.map((s) => s.segments.find((g) => varFor(fx.var, g.overlay)));

describe("VAR chapter", () => {
  it("every show has one, built from var_offside, with its check timing", () => {
    for (const seg of varChapters) {
      expect(seg).toBeDefined();
      const o = seg!.overlay;
      expect(validate("overlay", o).errors).toEqual([]);
      expect(o.claims.map((c) => c.tool_call.name)).toEqual(["var_offside"]);
      expect(o.strokes.map((s) => s.shape)).toContain("offside_line");
      const m = varFor(fx.var, o)!;
      expect(m.decision_t).toBeGreaterThan(m.check_t);
      expect(evidenceFor(fx.evidence, o.claims[0])?.check).toBe("match");
    }
  });

  it("is provisional (amber dashed line) until the decision cue, then shows the decision", () => {
    const o = varChapters[0]!.overlay;
    const m = varFor(fx.var, o)!;
    const at = o.script.cues.find((c) => c.cue_id === m.decision_cue)!.offset_ms;
    const line = (ms: number) => varGraphics(m, o, ms).strokes.find((s) => s.shape === "offside_line")!;
    expect(isProvisional(m, o, at - 1)).toBe(true);
    expect(line(at - 1).style).toMatchObject({ color: "danger", dash: true });
    expect(varBanner(m, true).title).toMatch(/provisional/i);
    expect(isProvisional(m, o, at)).toBe(false);
    expect(line(at)).toEqual(o.strokes.find((s) => s.shape === "offside_line"));
    expect(varBanner(m, false).title).toBe("VAR · Goal stands");
  });
});

describe("moments that decided it", () => {
  const sums = Object.values(fx.summaries ?? {});
  it("has half-time and catch-up from B's tools, at most three moments, best first", () => {
    expect(Object.keys(fx.summaries ?? {}).sort()).toEqual(["catch_up", "half_time"]);
    for (const s of sums) {
      const ms = decidingMoments(s);
      expect(ms.length).toBeGreaterThan(0);
      expect(ms.length).toBeLessThanOrEqual(3);
      expect(ms.map((m) => m.rank)).toEqual([...ms.map((m) => m.rank)].sort((a, b) => a - b));
      expect(s.stats.home.goals).toBe(s.score.home);
      expect(validate("overlay", geometryOverlay(s.geometry, s.at_t, "x")).errors).toEqual([]);
    }
  });

  it("each moment replays with frames across its window, its shot re-run checked", () => {
    for (const s of sums)
      for (const m of s.moments) {
        const r = m.replay.replay;
        expect(r.start_t).toBeLessThanOrEqual(m.t);
        expect(r.end_t).toBeGreaterThanOrEqual(m.t);
        for (let t = r.start_t; t <= r.end_t; t += 500) expect(frameBetween(fx.frames, t)!.t).toBe(t);
        if (m.xg != null) expect(m.replay).toMatchObject({ tool: "shot_xg", check: "match" });
      }
  });

  it("the half-time goal is the VAR-checked one", () => {
    const goal = fx.summaries!.half_time!.moments.find((m) => m.kind === "goal")!;
    const m = varFor(fx.var, varChapters[0]!.overlay)!;
    expect(goal.var?.check_t).toBe(m.check_t);
  });
});
