import { describe, expect, it } from "vitest";
import type { Frame, Overlay } from "@chalktalk/contracts";
import { catchUpAt } from "../src/catchup";
import { eventStats, ingest, involves, playerLabel, rosterOf, SPRINT_MS, statsUpTo } from "../src/myplayer";
import type { Summary } from "../src/summary";

const sm = (kind: Summary["kind"], at_t: number) => ({ kind, at_t }) as Summary;

describe("catch me up", () => {
  const summaries = { half_time: sm("half_time", 300_000), catch_up: sm("catch_up", 600_000) };

  it("picks the latest summary at or before t", () => {
    expect(catchUpAt(summaries, 450_000)).toEqual({ kind: "ready", summary: summaries.half_time });
    expect(catchUpAt(summaries, 600_000)).toEqual({ kind: "ready", summary: summaries.catch_up });
    expect(catchUpAt(summaries, 9_000_000)).toEqual({ kind: "ready", summary: summaries.catch_up });
  });

  it("says when the first one lands if none is due yet", () => {
    expect(catchUpAt(summaries, 299_999)).toEqual({ kind: "not-yet", nextT: 300_000 });
  });

  it("says there is none when the data has no summaries", () => {
    expect(catchUpAt(undefined, 1000)).toEqual({ kind: "none" });
    expect(catchUpAt({}, 1000)).toEqual({ kind: "none" });
  });
});

/** Frames of one home player at 25 fps, moving `speed` m/s along x. */
function run(from: number, n: number, speed: (i: number) => number, id = "H09"): Frame[] {
  const out: Frame[] = [];
  let x = 0;
  for (let i = 0; i < n; i++) {
    const v = speed(i);
    if (i) x += v * 0.04;
    out.push({ t: from + i * 40, period: 1, ball: { x: 0, y: 0, z: 0, v: 0, owner: null }, players: [{ id, team: "home", x, y: 0, v, heading: 0 }] } as Frame);
  }
  return out;
}

describe("my player stats", () => {
  it("adds up distance over consecutive frames", () => {
    const s = statsUpTo(run(0, 26, () => 5), "H09", Infinity)!;
    expect(s.distanceM).toBeCloseTo(5, 6);
    expect(s.seenMs).toBe(1000);
    expect(s.topSpeed).toBe(5);
  });

  it("stops at match time t", () => {
    const s = statsUpTo(run(0, 51, () => 5), "H09", 1000)!;
    expect(s.distanceM).toBeCloseTo(5, 6);
  });

  it("counts no distance across a gap in the data", () => {
    const a = run(0, 26, () => 4);
    const b = run(10_000, 26, () => 4).map((f) => ({ ...f, players: f.players.map((p) => ({ ...p, x: p.x + 30 })) }));
    const s = statsUpTo([...a, ...b], "H09", Infinity)!;
    expect(s.distanceM).toBeCloseTo(8, 6);
    expect(s.seenMs).toBe(2000);
  });

  it("counts a sprint once it is held for a second, and only once", () => {
    // 2 s at sprint speed, 1 s jogging, 0.6 s at sprint speed (too short).
    const speed = (i: number) => (i < 50 ? SPRINT_MS + 1 : i < 75 ? 3 : SPRINT_MS + 1);
    expect(statsUpTo(run(0, 90, speed), "H09", Infinity)!.sprints).toBe(1);
    expect(statsUpTo(run(0, 30, () => SPRINT_MS + 1), "H09", Infinity)!.sprints).toBe(1);
    expect(statsUpTo(run(0, 20, () => SPRINT_MS + 1), "H09", Infinity)!.sprints).toBe(0);
  });

  it("does not count a re-sent batch twice", () => {
    const frames = run(0, 26, () => 5);
    const tracks = ingest(new Map(), frames);
    ingest(tracks, frames);
    expect(tracks.get("H09")!.distanceM).toBeCloseTo(5, 6);
  });

  it("returns null for a player not in the frames", () => {
    expect(statsUpTo(run(0, 5, () => 1), "A04", Infinity)).toBeNull();
  });

  it("counts touches and the last action from events where the player is the main actor", () => {
    const events = [
      { t: 100, type: "pass", actors: ["H09", "H10"] },
      { t: 200, type: "press", actors: ["A02", "H09"] },
      { t: 300, type: "shot", actors: ["H09"] },
      { t: 400, type: "goal", actors: ["H09"] },
      { t: 900, type: "carry", actors: ["H09"] },
    ];
    expect(eventStats(events, "H09", 500)).toEqual({ touches: 2, last: events[3] });
    expect(eventStats(events, "H09", 50)).toEqual({ touches: 0, last: null });
  });
});

describe("my player labels and breakdowns", () => {
  const roster = rosterOf({ teams: { home: { players: [{ id: "H09", number: 9, name: "Corrow" }] } } });

  it("labels with number and name from the roster, else the number from the id", () => {
    expect(playerLabel("H09", roster)).toBe("#9 Corrow");
    expect(playerLabel("H07", roster)).toBe("#7");
    expect(playerLabel("REF")).toBe("REF");
    expect(rosterOf(null).size).toBe(0);
  });

  it("finds a player in a breakdown's strokes or tool calls", () => {
    const ov = (pid: string | undefined, arg: string) =>
      ({ strokes: [{ geometry_m: { player_id: pid, points: [] } }], claims: [{ tool_call: { args: { player: arg, t: 1 } } }] }) as unknown as Overlay;
    expect(involves(ov("H09", "A01"), "H09")).toBe(true);
    expect(involves(ov(undefined, "H09"), "H09")).toBe(true);
    expect(involves(ov("H08", "A01"), "H09")).toBe(false);
  });
});
