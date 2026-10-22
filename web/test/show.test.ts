import { describe, expect, it } from "vitest";
import { validate, type Show } from "@chalktalk/contracts";
import raw from "../public/fixtures/show-sim-7.json?raw";
import { breakdownDurationMs, frameAt } from "../src/playback";
import { PRE_ROLL_MS, chaptersOf, pickShow, showStateAt, type ShowFixture } from "../src/show";

const fx: ShowFixture = JSON.parse(raw);
const BASE = "http://x.test/fixtures/show-sim-7/";

describe("show fixture", () => {
  it("holds postmatch shows that pass the show contract", () => {
    expect(fx.shows.length).toBe(9);
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

describe("chapters", () => {
  const show = pickShow(fx.shows, "analyst", "away")!;
  const { chapters, totalMs } = chaptersOf(show, BASE);

  it("picks by lens and side, falling back to the lens", () => {
    expect([show.lens, show.side]).toEqual(["analyst", "away"]);
    const other = { ...fx.shows[0], lens: "casual" as const, side: "home" as const };
    expect(pickShow([other], "newcomer", "away")).toBe(other);
    expect(pickShow([], "casual", "home")).toBeUndefined();
  });

  it("runs a pre-roll then the breakdown, back to back, in segment order", () => {
    expect(chapters.map((c) => c.title)).toEqual(show.segments.map((s) => s.chapter_title));
    let at = 0;
    for (const c of chapters) {
      expect(c.at).toBe(at);
      expect(c.preRollMs).toBe(PRE_ROLL_MS);
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
    expect(chapters[0].overlay.script.audio_url).toBeUndefined();
  });
});
