// Demo mode (judge UX): with no producer on shift, the public broadcast airs the crew's cached,
// gate-passed overlays at their minute on its own. Client side only; the hub is unchanged.
// A producer's decision on a moment (approve, override or reject) always wins over the demo.
import type { Overlay } from "@chalktalk/contracts";

/** The queue's overlays that passed the fact-check gate, marked as auto-approved by the demo. */
export function demoOverlays(queue: { overlays: Overlay[] } | null | undefined): Overlay[] {
  return (queue?.overlays ?? [])
    .filter((o) => o.gate?.passed)
    .map((o) => ({ ...o, approval: { state: "auto", by: "demo", at: null } }) as Overlay);
}

/**
 * The hub's overlays plus the demo's, for moments no producer has decided. A moment is the
 * overlay's `match_tc`: once any telling of it has a decision on the hub, the demo drops all of
 * its tellings, so a rejection keeps it off air and an approval airs the producer's version.
 */
export function withDemo(live: Overlay[], demo: Overlay[]): Overlay[] {
  const decided = new Set(live.filter((o) => (o.approval?.state ?? "pending") !== "pending").map((o) => o.match_tc));
  const extra = demo.filter((o) => !decided.has(o.match_tc));
  const ids = new Set(extra.map((o) => o.id));
  return [...live.filter((o) => !ids.has(o.id)), ...extra];
}

export type AirStatus = { kind: "on-air" } | { kind: "next"; at: number } | { kind: "none" } | { kind: "full-time" };

/** What the broadcast pill says: on air now, the next moment's minute, or that none are left. */
export function airStatus(overlays: Overlay[], matchT: number, onAir: boolean, ended: boolean): AirStatus {
  if (onAir) return { kind: "on-air" };
  if (ended) return { kind: "full-time" };
  const next = overlays.map((o) => o.match_tc).filter((t) => t >= matchT).sort((a, b) => a - b)[0];
  return next === undefined ? { kind: "none" } : { kind: "next", at: next };
}
