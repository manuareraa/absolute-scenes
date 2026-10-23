// "Catch me up": one press takes the viewer to the latest summary the match data already has
// (catch-up or half-time) at or before the time on screen. Nothing is generated in the browser.
import type { Summaries, Summary } from "./summary";

export type CatchUp = { kind: "ready"; summary: Summary } | { kind: "not-yet"; nextT: number | null } | { kind: "none" };

/** The latest summary as of match time `t`; else when the first one lands, if the data has one. */
export function catchUpAt(summaries: Summaries | undefined, t: number): CatchUp {
  const all = Object.values(summaries ?? {}).filter((s): s is Summary => !!s && typeof s.at_t === "number");
  if (!all.length) return { kind: "none" };
  const due = all.filter((s) => s.at_t <= t).sort((a, b) => b.at_t - a.at_t)[0];
  if (due) return { kind: "ready", summary: due };
  const next = all.sort((a, b) => a.at_t - b.at_t)[0];
  return { kind: "not-yet", nextT: next ? next.at_t : null };
}
