import type { Counterfactual } from "./ask";

export type DuelResult = "you" | "ai" | "draw";

/** The Critic's own ranking: kept beats dropped, then the higher `net` (better minus worse). */
const score = (cf: Counterfactual | null) => (cf ? (cf.accepted ? 1000 : 0) + (cf.net ?? 0) : -1000);

/** "You vs the Tactician": who had the better idea, by the Critic's measured re-run. */
export function duelWinner(mine: Counterfactual | null, ai: Counterfactual | null): DuelResult {
  const d = score(mine) - score(ai);
  return d > 0 ? "you" : d < 0 ? "ai" : "draw";
}
