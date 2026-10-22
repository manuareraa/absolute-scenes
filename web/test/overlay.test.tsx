import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { strokeStartMs } from "@chalktalk/contracts";
import { OverlayLayer, StrokeShape } from "../src/components/OverlayLayer";
import { PitchView } from "../src/components/PitchView";
import { makeFixture } from "../src/fixture/synthetic";
import { frameAt } from "../src/playback";

const fx = makeFixture();
const all = fx.overlays.filter((o) => o.surface === "broadcast" && o.lens === "analyst");

describe("overlay renderer", () => {
  it.each(all.flatMap((o) => o.strokes.map((s) => [s.shape, o, s] as const)))("draws %s", (_shape, o, s) => {
    const html = renderToStaticMarkup(
      <svg>
        <StrokeShape stroke={s} frame={frameAt(fx.frames, o.match_tc)} k={1} />
      </svg>,
    );
    expect(html).toContain(`data-shape="${s.shape}"`);
  });

  it("shows only strokes whose start time has passed", () => {
    const o = all[0];
    const first = Math.min(...o.strokes.map((s) => strokeStartMs(o.script.cues, s)));
    const frame = frameAt(fx.frames, o.match_tc);
    const count = (ms: number) => (renderToStaticMarkup(<svg><OverlayLayer overlay={o} frame={frame} audioMs={ms} /></svg>).match(/data-stroke=/g) ?? []).length;
    expect(count(first - 1)).toBe(0);
    expect(count(first)).toBe(1);
    expect(count(60_000)).toBe(o.strokes.length);
  });

  it("follows the player for ring strokes", () => {
    const ring = all[0].strokes.find((s) => s.shape === "ring")!;
    const frame = frameAt(fx.frames, all[0].match_tc)!;
    const p = frame.players.find((q) => q.id === ring.geometry_m.player_id)!;
    const html = renderToStaticMarkup(<svg><StrokeShape stroke={ring} frame={frame} k={1} /></svg>);
    expect(html).toContain(`cx="${p.x}"`);
    expect(html).toContain(`cy="${-p.y}"`);
  });

  it("renders all players and the ball", () => {
    const html = renderToStaticMarkup(<PitchView frame={fx.frames[0]} />);
    expect((html.match(/class="player /g) ?? []).length).toBe(23);
    expect(html).toContain('class="ball"');
  });
});
