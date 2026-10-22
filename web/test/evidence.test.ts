import { describe, expect, it } from "vitest";
import { validate } from "@chalktalk/contracts";
import raw from "../public/fixtures/show-sim-7.json?raw";
import { claimForWord, claimWords, evidenceFor, evidenceOverlay, frameBetween, replayMatchT, REPLAY_HOLD_MS } from "../src/evidence";
import { strokeProgress } from "../src/playback";
import type { ShowFixture } from "../src/show";

const fx: ShowFixture = JSON.parse(raw);
const overlays = fx.shows.flatMap((s) => s.segments.map((g) => g.overlay));

describe("evidence fixture", () => {
  it("has an entry for every claim in every show", () => {
    for (const o of overlays) for (const c of o.claims) expect(evidenceFor(fx.evidence, c), `${o.id} ${c.id}`).toBeDefined();
  });

  it("the ghost's numbers re-run through B's evidence tool with the same hash", () => {
    const ghost = overlays.find((o) => o.claims.some((c) => c.tool_call.name === "ghost"))!;
    for (const c of ghost.claims) expect(evidenceFor(fx.evidence, c)).toMatchObject({ check: "match", hash_match: true });
  });

  it("has frames across every replay window, and draws as a valid overlay", () => {
    for (const [h, e] of Object.entries(fx.evidence!)) {
      for (let t = e.replay.start_t; t <= e.replay.end_t; t += 500) {
        expect(frameBetween(fx.frames, t)!.t, h).toBe(t);
      }
      const o = evidenceOverlay(e, "c1");
      expect(validate("overlay", o).errors).toEqual([]);
      for (const s of o.strokes) expect(strokeProgress(o, s, Infinity)).toBe(1);
    }
  });
});

describe("tapping numbers", () => {
  const o = overlays.find((ov) => ov.claims.some((c) => c.text_slot === "gap_m"))!;
  const gap = o.claims.find((c) => c.text_slot === "gap_m")!;

  it("maps a spoken number to its claim at the word's precision", () => {
    expect(claimForWord(o, `${Number(gap.value).toFixed(1)},`)).toBe(gap);
    expect(claimForWord(o, "metres")).toBeUndefined();
    expect(claimForWord(o, "999")).toBeUndefined();
  });

  it("puts every claim on exactly one spoken word", () => {
    for (const ov of overlays) {
      const spoken = [...claimWords(ov).values()];
      expect(spoken.sort((a, b) => a.id.localeCompare(b.id)), ov.id).toEqual([...ov.claims].sort((a, b) => a.id.localeCompare(b.id)));
    }
  });

  it("does not take a shirt number for a nearby measurement", () => {
    const ghost = overlays.find((ov) => ov.claims.some((c) => c.tool_call.name === "ghost"))!;
    const words = ghost.script.words!.map((w) => w.text);
    const tapped = [...claimWords(ghost).keys()].map((i) => words[i]);
    expect(tapped).not.toContain(words[words.indexOf("number") + 1]);
  });
});

describe("replay clock", () => {
  const e = { replay: { start_t: 1000, end_t: 5000 } } as Parameters<typeof replayMatchT>[0];
  it("plays the window, holds the end, then loops", () => {
    expect(replayMatchT(e, 0)).toBe(1000);
    expect(replayMatchT(e, 2500)).toBe(3500);
    expect(replayMatchT(e, 4000 + REPLAY_HOLD_MS / 2)).toBe(5000);
    expect(replayMatchT(e, 4000 + REPLAY_HOLD_MS + 10)).toBe(1010);
  });

  it("eases player positions between sparse frames", () => {
    const [a, b] = [fx.frames[0], fx.frames[1]];
    const mid = frameBetween([a, b], (a.t + b.t) / 2)!;
    expect(mid.players[0].x).toBeCloseTo((a.players[0].x + b.players.find((p) => p.id === a.players[0].id)!.x) / 2);
  });
});
