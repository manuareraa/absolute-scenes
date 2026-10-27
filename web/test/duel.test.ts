import { describe, expect, it } from "vitest";
import type { Counterfactual } from "../src/ask";
import { duelWinner } from "../src/duel";

const cf = (accepted: boolean, net: number): Counterfactual => ({ proposal: "x", accepted, metrics: [], net });

describe("You vs the Tactician", () => {
  it("a kept idea beats a dropped one, whatever the net", () => {
    expect(duelWinner(cf(true, 1), cf(false, 2))).toBe("you");
    expect(duelWinner(cf(false, 2), cf(true, 1))).toBe("ai");
  });
  it("between two kept or two dropped ideas, the higher net wins", () => {
    expect(duelWinner(cf(true, 2), cf(true, 1))).toBe("you");
    expect(duelWinner(cf(false, -1), cf(false, 0))).toBe("ai");
  });
  it("an equal score is a draw", () => {
    expect(duelWinner(cf(true, 1), cf(true, 1))).toBe("draw");
  });
  it("no idea tested loses to any tested idea", () => {
    expect(duelWinner(null, cf(false, -2))).toBe("ai");
    expect(duelWinner(cf(false, -2), null)).toBe("you");
    expect(duelWinner(null, null)).toBe("draw");
  });
});
