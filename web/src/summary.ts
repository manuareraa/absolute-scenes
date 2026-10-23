// Half-time and catch-up (M8): "the moments that decided it", from B's `half_time` and
// `catch_up` tools. Each moment carries its own replay entry (`show_fixture.py`), so tapping a
// card replays it on the pitch through the evidence panel.
import type { Overlay } from "@chalktalk/contracts";
import type { EvidenceEntry } from "./evidence";

type Stroke = Overlay["strokes"][number];

export interface TeamStats {
  goals: number;
  shots: number;
  on_target: number;
  xg: number;
  passes: number;
  pass_accuracy: number;
  possession: number;
  offsides: number;
  fouls: number;
  cards: number;
}

export interface Moment {
  rank: number;
  kind: "goal" | "chance" | "card" | "offside" | string;
  t: number;
  team: "home" | "away" | string;
  headline: string;
  xg?: number | null;
  score_after?: { home: number; away: number } | null;
  var?: { check_t: number; decision: string } | null;
  /** Player ids in the moment, main actor first. */
  actors?: string[];
  replay: EvidenceEntry;
}

export interface Summary {
  kind: "half_time" | "catch_up";
  /** Match time the summary is as of. */
  at_t: number;
  score: { home: number; away: number };
  stats: { home: TeamStats; away: TeamStats };
  geometry: Pick<Stroke, "shape" | "geometry_m" | "style">[];
  moments: Moment[];
}

export type Summaries = Partial<Record<Summary["kind"], Summary>>;

/** At most three moments, best first. */
export const decidingMoments = (s: Summary) => [...s.moments].sort((a, b) => a.rank - b.rank).slice(0, 3);

export const summaryTitle = (s: Summary, clock: (ms: number) => string) =>
  s.kind === "half_time" ? "Half-time: the moments that decided it" : `Catch-up at ${clock(s.at_t)}: what you missed`;

/** Possession and pass accuracy come as 0..1 shares. */
export const pct = (x: number) => `${Math.round(x * 100)}%`;
