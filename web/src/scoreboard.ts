// Score bug and momentum strip: built only from goals and shots the match data records. The show
// fixture has no full event stream, so its goals and shots come from the summary moments and the
// evidence replays; the live hub sends every event in its frame batches.
import type { ShowFixture } from "./show";

export interface Goal {
  t: number;
  team: string;
}

export interface Shot {
  t: number;
  team: string;
  /** The shot's xG, when the data carries it. */
  xg?: number;
}

type Score = { home: number; away: number };

/** Unique by time and team, sorted by time, so an event seen twice counts once. */
function uniq<T extends { t: number; team: string }>(xs: T[]): T[] {
  const seen = new Map<string, T>();
  for (const x of xs) {
    const k = `${x.t}:${x.team}`;
    const had = seen.get(k);
    // Keep the copy that carries the most detail (an xG beats none).
    if (!had || Object.keys(x).length > Object.keys(had).length) seen.set(k, x);
  }
  return [...seen.values()].sort((a, b) => a.t - b.t);
}

const sides = (team: unknown): team is "home" | "away" => team === "home" || team === "away";

/** Every goal and shot in a show fixture's summaries and evidence replays. */
export function showEvents(fx: Pick<ShowFixture, "evidence" | "summaries">): { goals: Goal[]; shots: Shot[] } {
  const goals: Goal[] = [];
  const shots: Shot[] = [];
  for (const sm of Object.values(fx.summaries ?? {})) {
    for (const m of sm.moments ?? []) {
      if (!sides(m.team)) continue;
      if (m.kind === "goal") goals.push({ t: m.t, team: m.team });
      const shotT = (m as { shot_t?: number }).shot_t;
      if (typeof shotT === "number") shots.push(typeof m.xg === "number" ? { t: shotT, team: m.team, xg: m.xg } : { t: shotT, team: m.team });
    }
  }
  for (const e of Object.values(fx.evidence ?? {})) {
    for (const x of e.events ?? []) {
      if (!sides(x.team)) continue;
      if (x.type === "goal") goals.push({ t: x.t, team: x.team });
      if (x.type === "shot") shots.push({ t: x.t, team: x.team });
    }
  }
  return { goals: uniq(goals), shots: uniq(shots) };
}

/** Goals and shots in match package events (the hub's batches, or the package's events.json). */
export function packageEvents(events: unknown[]): { goals: Goal[]; shots: Shot[] } {
  const goals: Goal[] = [];
  const shots: Shot[] = [];
  for (const e of events as { t?: unknown; type?: unknown; team?: unknown; xg?: unknown; attrs?: { xg?: unknown } }[]) {
    if (!e || typeof e.t !== "number" || !sides(e.team)) continue;
    if (e.type === "goal") goals.push({ t: e.t, team: e.team });
    if (e.type === "shot") {
      // The package keeps a shot's xG in its attrs.
      const xg = e.attrs?.xg ?? e.xg;
      shots.push(typeof xg === "number" ? { t: e.t, team: e.team, xg } : { t: e.t, team: e.team });
    }
  }
  return { goals, shots };
}

/** The score after every goal up to and including match time `t`. */
export function scoreAt(goals: Goal[], t: number): Score {
  const score = { home: 0, away: 0 };
  for (const g of goals) if (g.t <= t && sides(g.team)) score[g.team]++;
  return score;
}

/** The match's last known time: summaries are "as of" a time, so they bound the match too. */
export function showEndT(fx: Pick<ShowFixture, "frames" | "summaries">): number {
  const last = fx.frames.length ? fx.frames[fx.frames.length - 1].t : 0;
  return Math.max(last, ...Object.values(fx.summaries ?? {}).map((s) => s.at_t));
}

export interface MomentumBin {
  /** Bin start, match ms. */
  t: number;
  home: number;
  away: number;
}

export interface Momentum {
  /** "xg" when every shot carries an xG, else "shots" (a count). */
  metric: "xg" | "shots";
  binMs: number;
  endT: number;
  bins: MomentumBin[];
  /** The largest single-side bin value over the whole match, for scaling; at least 1 shot or 0.1 xG. */
  peak: number;
}

/**
 * Attacking momentum: each side's shots (summed xG, or a count when any xG is missing) in fixed
 * bins of match time, up to `endT`. Only shots at or before `nowT` count, so it never shows ahead.
 */
export function momentum(shots: Shot[], endT: number, nowT: number, binMs = 60_000): Momentum {
  const metric = shots.length && shots.every((s) => typeof s.xg === "number") ? "xg" : "shots";
  const n = Math.max(1, Math.ceil(endT / binMs));
  const fill = (upTo: number) => {
    const bins: MomentumBin[] = Array.from({ length: n }, (_, i) => ({ t: i * binMs, home: 0, away: 0 }));
    for (const s of shots) {
      if (s.t > upTo || s.t < 0 || !sides(s.team)) continue;
      bins[Math.min(n - 1, Math.floor(s.t / binMs))][s.team] += metric === "xg" ? s.xg! : 1;
    }
    return bins;
  };
  // The scale comes from the whole match, so bars keep their size as the clock runs.
  const top = Math.max(0, ...fill(Infinity).flatMap((b) => [b.home, b.away]));
  return { metric, binMs, endT: n * binMs, bins: fill(nowT), peak: Math.max(top, metric === "xg" ? 0.1 : 1) };
}
