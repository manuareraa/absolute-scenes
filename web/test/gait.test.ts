import { describe, expect, it } from "vitest";
import { angleGap, footPose, pickClip, pickFacing, STRIDE_M, stepGait, type Gait, type PlayerState } from "../src/figures/gait";

const run = (v: number, heading = 0, body_heading?: number, steps = 200, dtMs = 40) => {
  const states: Gait[] = [];
  let g: Gait | undefined;
  for (let k = 0; k < steps; k++) {
    const t = k * dtMs;
    const r = (heading * Math.PI) / 180;
    const d = (v * t) / 1000;
    const p: PlayerState = { id: "h1", team: "home", x: Math.cos(r) * d, y: Math.sin(r) * d, v, heading, body_heading };
    g = stepGait(g, p, t);
    states.push(g);
  }
  return states;
};

describe("gait clip", () => {
  it("picks the clip from speed", () => {
    expect([0, 1.5, 3.5, 7].map(pickClip)).toEqual(["idle", "walk", "jog", "sprint"]);
  });

  it("picks the facing from heading against body heading", () => {
    expect(angleGap(170, -170)).toBe(20);
    expect(pickFacing(0, 20)).toBe("forward");
    expect(pickFacing(0, 90)).toBe("side");
    expect(pickFacing(10, -170)).toBe("back");
  });
});

describe("no foot sliding", () => {
  for (const [v, heading, body] of [
    [1.5, 0, undefined],
    [3.5, 30, undefined],
    [7.5, -120, undefined],
    [3, 90, -90], // backpedal
    [2.5, 0, 90], // side-step
  ] as const) {
    it(`keeps a planted foot still at ${v} m/s, heading ${heading}`, () => {
      const states = run(v, heading, body);
      let stanceFrames = 0;
      for (let k = 1; k < states.length; k++) {
        for (const i of [0, 1]) {
          const a = states[k - 1].feet[i];
          const b = states[k].feet[i];
          if (a.stance && b.stance && a.at === b.at) {
            const pa = footPose(states[k - 1], i);
            const pb = footPose(states[k], i);
            expect(Math.hypot(pb.x - pa.x, pb.y - pa.y)).toBe(0);
            expect(pb.z).toBe(0);
            stanceFrames++;
          }
        }
      }
      expect(stanceFrames).toBeGreaterThan(states.length / 2);
    });
  }

  it("steps at the stride rate, so a planted foot stays under the body", () => {
    for (const v of [1.5, 3.5, 7.5]) {
      const states = run(v);
      const clip = states[10].clip;
      for (const g of states.slice(5))
        for (const i of [0, 1]) {
          const f = footPose(g, i);
          expect(Math.abs(f.x - g.x)).toBeLessThanOrEqual(STRIDE_M[clip] / 4 + 1e-9 + (v * 0.04) / 1);
        }
      // Cycles covered match distance / stride.
      const plants = states.filter((g, k) => k && g.feet[0].stance && !states[k - 1].feet[0].stance).length;
      const expected = (v * 0.04 * states.length) / STRIDE_M[clip];
      expect(Math.abs(plants - expected)).toBeLessThanOrEqual(1);
    }
  });

  it("holds the pose on a frozen frame and starts fresh after a seek", () => {
    const states = run(3.5, 0, undefined, 20);
    const last = states[states.length - 1];
    const p: PlayerState = { id: "h1", team: "home", x: last.x, y: last.y, v: 3.5, heading: 0 };
    expect(stepGait(last, p, last.t)).toBe(last);
    const back = stepGait(last, p, last.t - 1000);
    expect(back.phase).toBe(0);
    const jump = stepGait(last, { ...p, x: last.x + 20 }, last.t + 40);
    expect(jump.phase).toBe(0);
    expect(jump.feet[0].stance).toBe(true);
  });
});
