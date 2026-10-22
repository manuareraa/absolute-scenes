import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { strokeStartMs } from "@chalktalk/contracts";
import { ghostPose } from "../src/components/Ghost";
import { OverlayLayer, StrokeShape } from "../src/components/OverlayLayer";
import { PitchView } from "../src/components/PitchView";
import { makeFixture } from "../src/fixture/synthetic";
import { dist, toVec } from "../src/pitch";
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

describe("ghost figure", () => {
  const o = all.find((ov) => ov.strokes.some((s) => s.shape === "ghost_path"))!;
  const ghost = o.strokes.find((s) => s.shape === "ghost_path")!;
  const frame = frameAt(fx.frames, o.match_tc);
  const pts = ghost.geometry_m.points!.map(toVec);

  it("walks along the path and stands at its end, tethered to the real player", () => {
    expect(ghostPose(ghost, frame, pts.slice(0, 2), 0.5)).toMatchObject({ at: pts[1], expected: pts[2], gapM: null });
    const done = ghostPose(ghost, frame, pts, 1)!;
    const p = frame!.players.find((q) => q.id === ghost.geometry_m.player_id)!;
    expect(done.actual).toMatchObject({ at: [p.x, p.y], team: p.team });
    expect(done.gapM).toBeCloseTo(dist([p.x, p.y], pts[2]), 6);
    const html = renderToStaticMarkup(<svg><StrokeShape stroke={ghost} frame={frame} k={1} /></svg>);
    expect(html).toContain(`data-ghost="${p.team}"`);
    expect(html).toContain(`${done.gapM!.toFixed(1)} m`);
  });

  it("draws an untethered ghost when the stroke names no player", () => {
    const bare = { ...ghost, geometry_m: { points: ghost.geometry_m.points } };
    expect(ghostPose(bare, frame, pts, 1)).toMatchObject({ actual: null, gapM: null });
    expect(renderToStaticMarkup(<svg><StrokeShape stroke={bare} frame={frame} k={1} /></svg>)).toContain('data-ghost="ghost"');
    expect(ghostPose(bare, frame, [], 0)).toBeNull();
  });
});
