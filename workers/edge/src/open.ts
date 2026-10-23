// The producer console is open to anyone (it is a prototype for judges), but without the
// shared secret a post can only decide an overlay that is already in the published queue
// fixture: the overlay is taken from that file and only its approval comes from the request.
// So no one without the secret can put their own text or drawing on air.

/** Clock actions the open producer needs for "Restart match". */
export const OPEN_ACTIONS = new Set(["reset", "play"]);

const STATES = new Set(["pending", "approved", "rejected", "overridden", "auto"]);

/** Where the queue fixture for a match sits in the static assets (`web/public/fixtures`). */
export const queueFile = (matchId: string) => `/fixtures/queue-${matchId}.json`;

export interface Approval {
  state: string;
  by: string | null;
  at: string | null;
}

/** A well-formed approval, or null. */
export function parseApproval(a: unknown): Approval | null {
  if (!a || typeof a !== "object") return null;
  const { state, by = null, at = null } = a as Record<string, unknown>;
  if (typeof state !== "string" || !STATES.has(state)) return null;
  if (by !== null && (typeof by !== "string" || by.length > 64)) return null;
  if (at !== null && (typeof at !== "string" || at.length > 40)) return null;
  return { state, by, at };
}

/** The queued overlay with the requested approval, or an error message. */
export function openDecision(
  queue: { match_id?: unknown; overlays?: unknown },
  matchId: string,
  overlay: { id: string; approval?: unknown },
): { overlay: Record<string, unknown> } | { error: string } {
  if (queue.match_id !== matchId || !Array.isArray(queue.overlays)) return { error: "no queue for this match" };
  const queued = (queue.overlays as { id?: unknown }[]).find((o) => o && o.id === overlay.id);
  if (!queued) return { error: "only overlays in the published queue can be decided without the crew key" };
  const approval = parseApproval(overlay.approval);
  if (!approval) return { error: "bad approval" };
  return { overlay: { ...(queued as Record<string, unknown>), approval } };
}
