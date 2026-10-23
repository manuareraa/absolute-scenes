// "My player": one player the viewer follows. Every number here is computed from the frames and
// events the app already holds; anything the data cannot give is reported as missing, never guessed.
import type { Frame, Overlay } from "@chalktalk/contracts";
import { shirtNumber } from "./pitch";

export const MY_PLAYER_KEY = "chalktalk.myPlayer";

/** A sprint: at least 25.2 km/h (7 m/s), held for at least 1 s (the usual tracking-provider definition). */
export const SPRINT_MS = 7;
export const SPRINT_MIN_MS = 1000;
/** Two frames further apart than this are a gap in the data: no distance is counted across it. */
export const MAX_GAP_MS = 200;

export interface RosterPlayer {
  id: string;
  number: number;
  name: string;
  team: string;
}

/** Players by id, from the match manifest (`/api/match/<id>`, written by `chalktalk_sim`). */
export function rosterOf(manifest: unknown): Map<string, RosterPlayer> {
  const out = new Map<string, RosterPlayer>();
  const teams = (manifest as { teams?: Record<string, { players?: unknown[] }> } | null)?.teams;
  for (const [team, t] of Object.entries(teams ?? {})) {
    for (const p of t?.players ?? []) {
      const { id, number, name } = (p ?? {}) as Partial<RosterPlayer>;
      if (typeof id === "string" && typeof name === "string") out.set(id, { id, number: typeof number === "number" ? number : (shirtNumber(id) ?? 0), name, team });
    }
  }
  return out;
}

/** "#9 Corrow" with a roster, else "#9" from the id; the id alone if it carries no number. */
export function playerLabel(id: string, roster?: Map<string, RosterPlayer>): string {
  const r = roster?.get(id);
  const n = r?.number ?? shirtNumber(id);
  if (r) return n ? `#${n} ${r.name}` : r.name;
  return n !== null ? `#${n}` : id;
}

/** Running totals for one player, built frame by frame. */
export interface Track {
  lastT: number;
  last?: { x: number; y: number; v: number };
  distanceM: number;
  /** Ms of data with this player in consecutive frames. */
  seenMs: number;
  sprints: number;
  topSpeed: number;
  /** Ms the current run has stayed above the sprint speed; -1 once it has counted. */
  fastMs: number;
}

const newTrack = (): Track => ({ lastT: -Infinity, distanceM: 0, seenMs: 0, sprints: 0, topSpeed: 0, fastMs: 0 });

/**
 * Add frames (sorted by t) to every player's track. Frames at or before a track's last time are
 * skipped, so a re-sent batch counts once. Mutates `tracks` for the live feed's sake.
 */
export function ingest(tracks: Map<string, Track>, frames: Frame[]): Map<string, Track> {
  for (const f of frames) {
    for (const p of f.players) {
      if (p.team === "ref") continue;
      const tr = tracks.get(p.id) ?? newTrack();
      if (f.t <= tr.lastT) continue;
      const dt = f.t - tr.lastT;
      const joined = tr.last !== undefined && dt <= MAX_GAP_MS;
      if (joined) {
        tr.distanceM += Math.hypot(p.x - tr.last!.x, p.y - tr.last!.y);
        tr.seenMs += dt;
      }
      // Slowing down, or a gap in the data, ends a run; a run counts once, after a second.
      if (!joined || p.v < SPRINT_MS) tr.fastMs = 0;
      else if (tr.fastMs >= 0) {
        tr.fastMs += dt;
        if (tr.fastMs >= SPRINT_MIN_MS) {
          tr.sprints++;
          tr.fastMs = -1;
        }
      }
      tr.topSpeed = Math.max(tr.topSpeed, p.v);
      tr.lastT = f.t;
      tr.last = { x: p.x, y: p.y, v: p.v };
      tracks.set(p.id, tr);
    }
  }
  return tracks;
}

export interface TrackStats {
  distanceM: number;
  sprints: number;
  /** m/s */
  topSpeed: number;
  seenMs: number;
}

/** One player's totals over the frames up to match time `t` (recorded playback). */
export function statsUpTo(frames: Frame[], id: string, t: number): TrackStats | null {
  let end = frames.length;
  while (end > 0 && frames[end - 1].t > t) end--;
  const tr = ingest(new Map(), frames.slice(0, end).map((f) => ({ ...f, players: f.players.filter((p) => p.id === id) }))).get(id);
  return tr ? { distanceM: tr.distanceM, sprints: tr.sprints, topSpeed: tr.topSpeed, seenMs: tr.seenMs } : null;
}

export interface MatchEvent {
  t: number;
  type: string;
  actors?: string[];
  team?: string;
}

/** Event types where the first actor plays the ball. */
const TOUCH_TYPES = new Set(["pass", "carry", "dribble", "shot", "save", "tackle", "interception", "clearance"]);

/** Touches (needs a full event stream) and the last action, from events up to `t` where `id` is the main actor. */
export function eventStats(events: MatchEvent[], id: string, t: number): { touches: number; last: MatchEvent | null } {
  let touches = 0;
  let last: MatchEvent | null = null;
  for (const e of events) {
    if (e.t > t || e.actors?.[0] !== id) continue;
    if (TOUCH_TYPES.has(e.type)) touches++;
    if (!last || e.t >= last.t) last = e;
  }
  return { touches, last };
}

/** True when a breakdown draws or measures this player: a stroke on them, or a tool call about them. */
export function involves(overlay: Pick<Overlay, "strokes" | "claims">, id: string): boolean {
  const onStroke = overlay.strokes.some((s) => (s.geometry_m as { player_id?: unknown }).player_id === id);
  return onStroke || overlay.claims.some((c) => Object.values(c.tool_call?.args ?? {}).some((v) => v === id || (Array.isArray(v) && v.includes(id))));
}

export function loadMyPlayer(): string | null {
  try {
    return localStorage.getItem(MY_PLAYER_KEY);
  } catch {
    return null;
  }
}

export function saveMyPlayer(id: string | null) {
  try {
    if (id) localStorage.setItem(MY_PLAYER_KEY, id);
    else localStorage.removeItem(MY_PLAYER_KEY);
  } catch {
    // Private windows may refuse storage; the pick then lasts for this visit only.
  }
}
