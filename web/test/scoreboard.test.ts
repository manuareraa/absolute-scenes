import { describe, expect, it } from "vitest";
import raw from "../public/fixtures/show-sim-7.json?raw";
import { momentum, scoreAt, showEndT, showEvents } from "../src/scoreboard";
import type { ShowFixture } from "../src/show";

const fx: ShowFixture = JSON.parse(raw);
const ev = showEvents(fx);

describe("score at a match time", () => {
  it("counts each goal from its own time on", () => {
    const goals = [
      { t: 1000, team: "home" },
      { t: 5000, team: "away" },
    ];
    expect(scoreAt(goals, 0)).toEqual({ home: 0, away: 0 });
    expect(scoreAt(goals, 999)).toEqual({ home: 0, away: 0 });
    expect(scoreAt(goals, 1000)).toEqual({ home: 1, away: 0 });
    expect(scoreAt(goals, 9000)).toEqual({ home: 1, away: 1 });
  });

  it("finds the show fixture's three goals once each", () => {
    expect(ev.goals).toEqual([
      { t: 185120, team: "home" },
      { t: 413760, team: "away" },
      { t: 539840, team: "home" },
    ]);
  });

  it("agrees with every summary's score at its own time", () => {
    for (const sm of Object.values(fx.summaries ?? {})) expect(scoreAt(ev.goals, sm.at_t)).toEqual(sm.score);
    expect(scoreAt(ev.goals, showEndT(fx))).toEqual({ home: 2, away: 1 });
  });
});

describe("momentum", () => {
  it("sums each side's xG per bin and never shows a shot before its time", () => {
    const shots = [
      { t: 30_000, team: "home", xg: 0.2 },
      { t: 50_000, team: "home", xg: 0.1 },
      { t: 70_000, team: "away", xg: 0.4 },
    ];
    const m = momentum(shots, 120_000, 60_000);
    expect(m.metric).toBe("xg");
    expect(m.bins).toHaveLength(2);
    expect(m.bins[0].home).toBeCloseTo(0.3);
    expect(m.bins[1].away).toBe(0); // 70 s is after now
    expect(m.peak).toBeCloseTo(0.4); // the scale holds for the whole match
    expect(momentum(shots, 120_000, 120_000).bins[1].away).toBeCloseTo(0.4);
  });

  it("counts shots when any shot has no xG", () => {
    const m = momentum([{ t: 10, team: "away" }, { t: 20, team: "away", xg: 0.5 }], 60_000, 60_000);
    expect(m.metric).toBe("shots");
    expect(m.bins[0]).toEqual({ t: 0, home: 0, away: 2 });
    expect(m.peak).toBe(1 + 1);
  });

  it("uses the xG of the show fixture's timed shots, which the summaries carry", () => {
    const m = momentum(ev.shots, showEndT(fx), Infinity);
    expect(m.metric).toBe("xg");
    const home = m.bins.reduce((a, b) => a + b.home, 0);
    // Every home shot is timed: the total matches the catch-up's home xG.
    expect(home).toBeCloseTo(fx.summaries!.catch_up!.stats.home.xg, 3);
  });
});
