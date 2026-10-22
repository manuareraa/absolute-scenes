// Producer console logic: a queue of crew overlays that a human approves or rejects before they
// go to air. Approving one that failed the Verifier gate records an override, not an approval.
import type { Frame, Overlay } from "@chalktalk/contracts";

export type Approval = Overlay["approval"];
export type Decision = "approve" | "reject";

/** Built by `web/scripts/show_fixture.py --queue`: the overlays and the frame at each moment. */
export interface QueueFixture {
  match_id: string;
  overlays: Overlay[];
  frames: Frame[];
}

/** Header the edge Worker checks on `POST /api/overlay` (`workers/edge/src/auth.ts`). */
export const SECRET_HEADER = "x-chalktalk-secret";

export const isOpen = (o: Overlay) => o.approval.state === "pending";
export const gatePassed = (o: Overlay) => o.gate?.passed ?? false;

/** The approval a decision records: approve, override (gate failed or missing) or reject. */
export function approvalFor(o: Overlay, decision: Decision, by: string, at: Date): Approval {
  const state = decision === "reject" ? "rejected" : gatePassed(o) ? "approved" : "overridden";
  return { state, by: by.trim() || null, at: at.toISOString() };
}

/** Overlays with recorded decisions applied, by overlay id. */
export function applyDecisions(overlays: Overlay[], decisions: Record<string, Approval>): Overlay[] {
  return overlays.map((o) => (decisions[o.id] ? { ...o, approval: decisions[o.id] } : o));
}

/** Open overlays first, then by moment, lens and side; `openOnly` hides decided ones. */
export function queueOrder(overlays: Overlay[], openOnly: boolean): Overlay[] {
  return overlays
    .filter((o) => !openOnly || isOpen(o))
    .sort((a, b) => Number(isOpen(b)) - Number(isOpen(a)) || a.match_tc - b.match_tc || a.lens.localeCompare(b.lens) || a.side.localeCompare(b.side));
}

/** Gate scores as rows, sorted by name. */
export function gateRows(o: Overlay): { name: string; score: number }[] {
  return Object.entries(o.gate?.scores ?? {})
    .map(([name, score]) => ({ name, score }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function counts(overlays: Overlay[]): Record<Approval["state"], number> {
  const c = { pending: 0, approved: 0, rejected: 0, overridden: 0, auto: 0 };
  for (const o of overlays) c[o.approval.state]++;
  return c;
}

/** Re-post a decided overlay to the match hub, which replaces it by id for every viewer. */
export async function postDecision(
  fetcher: typeof fetch,
  matchId: string,
  overlay: Overlay,
  secret: string,
): Promise<{ ok: boolean; status: number }> {
  const r = await fetcher("/api/overlay", {
    method: "POST",
    headers: { "content-type": "application/json", [SECRET_HEADER]: secret },
    body: JSON.stringify({ match_id: matchId, overlay }),
  });
  return { ok: r.ok, status: r.status };
}

/** Every open telling (lens, side, language) of the overlay's moment, so a viewer on any
 * setting sees it once the moment is approved. */
export const momentTellings = (all: Overlay[], o: Overlay) => all.filter((x) => x.match_tc === o.match_tc && isOpen(x));

/** Overlays the hub has that the queue fixture lacks (the crew's live posts), added to the queue. */
export function mergeQueue(fixture: Overlay[], live: Overlay[]): Overlay[] {
  const ids = new Set(fixture.map((o) => o.id));
  return [...fixture, ...live.filter((o) => !ids.has(o.id))];
}

/** The overlay back in the queue, so the hub stops airing it (re-posting an id replaces it). */
export const withdrawn = (o: Overlay): Overlay => ({ ...o, approval: { state: "pending", by: null, at: null } });

/** Restart the match on the hub (`reset` puts the clock at 0, paused; `play` starts it). */
export async function restartMatch(fetcher: typeof fetch, matchId: string, secret: string): Promise<{ ok: boolean; status: number }> {
  for (const action of ["reset", "play"]) {
    const r = await fetcher(`/api/match/${encodeURIComponent(matchId)}/control`, {
      method: "POST",
      headers: { "content-type": "application/json", [SECRET_HEADER]: secret },
      body: JSON.stringify({ action }),
    });
    if (!r.ok) return { ok: false, status: r.status };
  }
  return { ok: true, status: 200 };
}

const KEY = (matchId: string) => `chalktalk.producer.${matchId}`;

/** Decisions survive a reload in this browser; storage can be missing or blocked. */
export function loadDecisions(matchId: string): Record<string, Approval> {
  try {
    return JSON.parse(localStorage.getItem(KEY(matchId)) ?? "{}");
  } catch {
    return {};
  }
}

export function saveDecisions(matchId: string, decisions: Record<string, Approval>): void {
  try {
    localStorage.setItem(KEY(matchId), JSON.stringify(decisions));
  } catch {
    // Private mode or blocked storage: decisions last for this page only.
  }
}
