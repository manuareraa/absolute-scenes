import { describe, expect, it } from "vitest";
import { BALL_CLEAR, DISC_GAP, MAX_NUDGE, arrowHead, dist, layoutDiscs, pathD, polylineLength, shirtNumber, toSvg, toVec, truncatePolyline, type Vec } from "../src/pitch";

describe("pitch geometry", () => {
  const L: Vec[] = [[0, 0], [10, 0], [10, 10]];

  it("reads shirt numbers from player ids", () => {
    expect(shirtNumber("H09")).toBe(9);
    expect(shirtNumber("A10")).toBe(10);
    expect(shirtNumber("h7")).toBe(7);
    expect(shirtNumber("REF")).toBeNull();
  });

  it("flips y into SVG space", () => {
    expect(toSvg([3, 4])).toEqual([3, -4]);
    expect(toVec(["1.5", 2] as unknown[])).toEqual([1.5, 2]);
  });

  it("measures and truncates polylines by length", () => {
    expect(polylineLength(L)).toBe(20);
    expect(truncatePolyline(L, 0.25)).toEqual([[0, 0], [5, 0]]);
    expect(truncatePolyline(L, 0.75)).toEqual([[0, 0], [10, 0], [10, 5]]);
    expect(truncatePolyline(L, 1)).toEqual(L);
    expect(truncatePolyline(L, 0)).toEqual([[0, 0]]);
  });

  it("builds path data and an arrowhead at the tip", () => {
    expect(pathD([[0, 0], [1, 2]])).toBe("M0.00 0.00 L1.00 -2.00");
    expect(arrowHead([[0, 0], [10, 0]])).toMatch(/^M10\.00 0\.00 /);
    expect(arrowHead([[0, 0]])).toBeNull();
  });

  it("parts overlapping discs a little and keeps the rest where they are", () => {
    const players: Vec[] = [[0, 0], [0.9, 0], [30, 10]];
    const at = layoutDiscs(players, [50, 30]);
    expect(dist(at.players[0], at.players[1])).toBeGreaterThan(0.9);
    at.players.forEach((p, i) => expect(dist(p, players[i])).toBeLessThanOrEqual(MAX_NUDGE + 1e-9));
    expect(at.players[2]).toEqual([30, 10]);
    expect(at.ball).toEqual([50, 30]);
    const far = layoutDiscs([[0, 0], [DISC_GAP + 1, 0]], [50, 30]);
    expect(far.players).toEqual([[0, 0], [DISC_GAP + 1, 0]]);
  });

  it("draws a ball at a player's feet just outside their disc, on its own side", () => {
    const at = layoutDiscs([[10, 0]], [10.55, 0]);
    expect(dist(at.ball, [10, 0])).toBeGreaterThanOrEqual(BALL_CLEAR - 1e-9);
    expect(dist(at.ball, [10.55, 0])).toBeLessThan(BALL_CLEAR);
    expect(at.ball[0]).toBeGreaterThan(10);
    expect(dist(layoutDiscs([[10, 0]], [10, 0], 1.6).ball, [10, 0])).toBeGreaterThanOrEqual(BALL_CLEAR * 1.6 - 1e-9);
    // Between two players, it clears both, not just the nearer one.
    const two = layoutDiscs([[0, 0], [3, 0]], [1.2, 0]);
    expect(Math.min(dist(two.ball, two.players[0]), dist(two.ball, two.players[1]))).toBeGreaterThanOrEqual(BALL_CLEAR - 1e-9);
  });
});
