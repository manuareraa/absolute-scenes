import { describe, expect, it } from "vitest";
import { validate } from "@chalktalk/contracts";
import committed from "../public/fixtures/demo-001.json?raw";
import { FPS, buildScript, makeFixture } from "../src/fixture/synthetic";

const fx = makeFixture();

describe("synthetic fixture", () => {
  it("matches the committed JSON (regenerate with npm run gen:fixture)", () => {
    expect(JSON.parse(committed)).toEqual(fx);
  });

  it("has 25 fps frames that pass the frame contract", () => {
    expect(fx.fps).toBe(FPS);
    fx.frames.forEach((f, i) => {
      expect(f.t).toBe(Math.round((i * 1000) / FPS));
    });
    for (const f of fx.frames.filter((_, i) => i % 25 === 0)) expect(validate("frame", f).errors).toEqual([]);
  });

  it("has overlays that pass the overlay contract and cover every shape", () => {
    for (const o of fx.overlays) expect(validate("overlay", o).errors).toEqual([]);
    const shapes = new Set(fx.overlays.flatMap((o) => o.strokes.map((s) => s.shape)));
    expect([...shapes].sort()).toEqual(
      ["arrow", "ghost_path", "label", "line", "offside_line", "pass_lane", "ring", "run", "spotlight", "zone"],
    );
  });

  it("binds every stroke to a cue in its script", () => {
    for (const o of fx.overlays) {
      const cues = new Set(o.script.cues.map((c) => c.cue_id));
      for (const s of o.strokes) expect(cues.has(s.cue_id)).toBe(true);
    }
  });

  it("uses only synthetic ids", () => {
    const ids = new Set(fx.frames[0].players.map((p) => p.id));
    for (const id of ids) expect(id).toMatch(/^(h|a)\d+$|^ref$/);
  });
});

describe("buildScript", () => {
  it("turns cue markers into cues, words and SSML bookmarks", () => {
    const s = buildScript("Look at the [k1:gap] now");
    expect(s.text).toBe("Look at the gap now");
    expect(s.cues).toEqual([{ cue_id: "k1", offset_ms: s.words![3].offset_ms }]);
    expect(s.ssml).toBe("<speak>Look at the <bookmark mark='k1'/>gap now</speak>");
  });
});
