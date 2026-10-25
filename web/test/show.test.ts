import { describe, expect, it } from "vitest";
import { validate, type Show } from "@chalktalk/contracts";
import raw from "../public/fixtures/show-sim-7.json?raw";
import { breakdownDurationMs, frameAt } from "../src/playback";
import { ghostPose } from "../src/components/Ghost";
import { toVec } from "../src/pitch";
import { FIRST_PRE_ROLL_MS, PRE_ROLL_MS, chaptersOf, pickShow, showStateAt, type ShowFixture } from "../src/show";

const fx: ShowFixture = JSON.parse(raw);
const BASE = "http://x.test/fixtures/show-sim-7/";

describe("show fixture", () => {
  it("holds postmatch shows that pass the show contract", () => {
    expect(fx.shows.length).toBe(18); // 9 per caption language
    for (const s of fx.shows) expect(validate("show", s).errors).toEqual([]);
  });

  it("has frames for every chapter's pre-roll", () => {
    for (const s of fx.shows) {
      for (const seg of s.segments) {
        const t = seg.overlay.match_tc;
        expect(t - frameAt(fx.frames, t - PRE_ROLL_MS)!.t).toBeLessThanOrEqual(PRE_ROLL_MS + 80);
        expect(t - frameAt(fx.frames, t)!.t).toBeLessThan(80);
      }
    }
  });
});

describe("ghost chapters", () => {
  const ghosts = fx.shows.map((s) => s.segments.find((g) => g.overlay.strokes.some((k) => k.shape === "ghost_path"))?.overlay);

  it("every show has one, matching its lens and side", () => {
    fx.shows.forEach((s, i) => expect(ghosts[i]).toMatchObject({ lens: s.lens, side: s.side, lang: s.lang }));
  });

  it("draws B's ghost tool output, with every number bound to that call", () => {
    const o = ghosts[0]!;
    expect(o.claims.map((c) => c.tool_call.name)).toEqual(["ghost", "ghost"]);
    expect(o.strokes.map((s) => s.shape)).toEqual(["ghost_path", "ring", "run"]);
    const ghost = o.strokes[0];
    const pts = ghost.geometry_m.points!.map(toVec);
    const pose = ghostPose(ghost, frameAt(fx.frames, o.match_tc), pts, 1)!;
    // The tether the viewer sees is the gap the pundit says, within the claim's tolerance.
    const gap = o.claims.find((c) => c.text_slot === "gap_m")!;
    expect(Math.abs(pose.gapM! - Number(gap.value))).toBeLessThanOrEqual(gap.tolerance!);
    expect(o.script.text).toContain(`${Number(gap.value).toFixed(1)} metres`);
  });
});

describe("chapters", () => {
  const show = pickShow(fx.shows, "analyst", "away")!;
  const { chapters, totalMs } = chaptersOf(show, BASE);

  it("draws both of line_gap's lines with each gap arrow, on the arrow's cue", () => {
    const segs = fx.shows.flatMap((s) => s.segments);
    let arrows = 0;
    for (const { overlay: o } of segs) {
      for (const s of o.strokes) {
        const c = o.claims.find((x) => s.claim_ids?.includes(x.id));
        if (s.shape !== "arrow" || c?.tool_call.name !== "line_gap") continue;
        arrows++;
        const lines = o.strokes.filter((x) => x.shape === "line" && x.id.startsWith(`${s.id}-line`));
        expect(lines).toHaveLength(2);
        for (const l of lines) expect(l.cue_id).toBe(s.cue_id);
      }
    }
    expect(arrows).toBeGreaterThan(0);
  });

  it("titles a shot that scored as a goal", () => {
    const titles = fx.shows.flatMap((s) => s.segments.map((g) => g.chapter_title));
    expect(titles.some((t) => t.includes("Goal"))).toBe(true);
  });

  it("picks by lens and side, falling back to the lens", () => {
    expect([show.lens, show.side]).toEqual(["analyst", "away"]);
    const other = { ...fx.shows[0], lens: "casual" as const, side: "home" as const };
    expect(pickShow([other], "newcomer", "away")).toBe(other);
    expect(pickShow([], "casual", "home")).toBeUndefined();
  });

  it("runs a pre-roll then the breakdown, back to back, in segment order, with a short first run-up", () => {
    expect(chapters.map((c) => c.title)).toEqual(show.segments.map((s) => s.chapter_title));
    let at = 0;
    for (const [i, c] of chapters.entries()) {
      expect(c.at).toBe(at);
      expect(c.preRollMs).toBe(i === 0 ? FIRST_PRE_ROLL_MS : PRE_ROLL_MS);
      expect(c.breakdownMs).toBe(breakdownDurationMs(c.overlay));
      at += c.preRollMs + c.breakdownMs;
    }
    expect(totalMs).toBe(at);
  });

  it("plays up to the moment, then holds on it on the audio clock", () => {
    const c = chapters[1];
    expect(showStateAt(chapters, totalMs, c.at)).toEqual({ chapter: 1, matchT: c.overlay.match_tc - PRE_ROLL_MS, overlay: null, audioMs: 0 });
    const mid = showStateAt(chapters, totalMs, c.at + PRE_ROLL_MS + 500);
    expect(mid).toMatchObject({ chapter: 1, matchT: c.overlay.match_tc, audioMs: 500 });
    expect(mid.overlay?.id).toBe(c.overlay.id);
    expect(showStateAt(chapters, totalMs, totalMs + c.at).chapter).toBe(1);
    expect(showStateAt([], 0, 10)).toEqual({ chapter: -1, matchT: 0, overlay: null, audioMs: 0 });
  });

  it("resolves relative audio against the fixture folder", () => {
    const seg = show.segments[0];
    const withAudio = { ...show, segments: [{ ...seg, audio_url: `audio/${seg.overlay.id}.mp3` }] as Show["segments"] };
    const [c] = chaptersOf(withAudio, BASE).chapters;
    expect(c.overlay.script.audio_url).toBe(`${BASE}audio/${seg.overlay.id}.mp3`);
    const { audio_url: _, ...script } = seg.overlay.script;
    const silent = { ...seg, audio_url: undefined, overlay: { ...seg.overlay, script } };
    const [none] = chaptersOf({ ...show, segments: [silent] as Show["segments"] }, BASE).chapters;
    expect(none.overlay.script.audio_url).toBeUndefined();
  });
});
