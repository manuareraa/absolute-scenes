import { describe, expect, it } from "vitest";
import { arrowHead, pathD, polylineLength, shirtNumber, toSvg, toVec, truncatePolyline, type Vec } from "../src/pitch";

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
});
