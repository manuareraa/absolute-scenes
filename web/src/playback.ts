// Playback clock: plays frames at 25 fps and holds the frame for each breakdown while its
// script plays on the audio clock (M1 has no audio yet, so the audio clock is wall time).
import { strokeStartMs, type Frame, type Overlay } from "@chalktalk/contracts";

type Stroke = Overlay["strokes"][number];

export const DEFAULT_LEAD_MS = 150;
export const DEFAULT_STROKE_MS = 600;
/** Hold after the last word or stroke before play resumes. */
export const TAIL_MS = 900;

/** Latest frame with `t <= matchT` (binary search; frames are sorted by t). */
export function frameAt(frames: Frame[], matchT: number): Frame | undefined {
  if (!frames.length) return undefined;
  let lo = 0;
  let hi = frames.length - 1;
  if (matchT <= frames[0].t) return frames[0];
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= matchT) lo = mid;
    else hi = mid - 1;
  }
  return frames[lo];
}

/** Draw-on progress 0..1 of a stroke at audio time `audioMs`; null before it starts. */
export function strokeProgress(overlay: Overlay, stroke: Stroke, audioMs: number): number | null {
  const start = strokeStartMs(overlay.script.cues, stroke);
  if (audioMs < start) return null;
  const dur = stroke.duration_ms ?? DEFAULT_STROKE_MS;
  return dur <= 0 ? 1 : Math.min(1, (audioMs - start) / dur);
}

/** How long a breakdown holds the frame: until the last word or stroke ends, plus a tail. */
export function breakdownDurationMs(overlay: Overlay): number {
  let end = 0;
  for (const w of overlay.script.words ?? []) end = Math.max(end, w.offset_ms + w.duration_ms);
  for (const c of overlay.script.cues) end = Math.max(end, c.offset_ms);
  for (const s of overlay.strokes) {
    end = Math.max(end, strokeStartMs(overlay.script.cues, s) + (s.duration_ms ?? DEFAULT_STROKE_MS));
  }
  return end + TAIL_MS;
}

/** Index of the word being spoken at `audioMs`, or -1. */
export function wordIndexAt(overlay: Overlay, audioMs: number): number {
  const words = overlay.script.words ?? [];
  let idx = -1;
  for (let i = 0; i < words.length; i++) if (words[i].offset_ms <= audioMs) idx = i;
  return idx;
}

export interface PlayState {
  matchT: number;
  overlay: Overlay | null;
  /** Audio clock inside the active breakdown, ms. */
  audioMs: number;
}

/**
 * Where playback is after `elapsedMs` of wall time, looping over the match. Overlays must
 * already be filtered to one per moment (surface and lens chosen).
 */
export function playStateAt(elapsedMs: number, matchEndMs: number, overlays: Overlay[]): PlayState {
  const moments = overlays
    .filter((o) => o.match_tc <= matchEndMs)
    .sort((a, b) => a.match_tc - b.match_tc)
    .map((o) => ({ o, dur: breakdownDurationMs(o) }));
  const loop = matchEndMs + moments.reduce((s, m) => s + m.dur, 0);
  let e = loop > 0 ? ((elapsedMs % loop) + loop) % loop : 0;
  let cursor = 0;
  for (const { o, dur } of moments) {
    const run = o.match_tc - cursor;
    if (e < run) return { matchT: cursor + e, overlay: null, audioMs: 0 };
    e -= run;
    cursor = o.match_tc;
    if (e < dur) return { matchT: cursor, overlay: o, audioMs: e };
    e -= dur;
  }
  return { matchT: Math.min(matchEndMs, cursor + e), overlay: null, audioMs: 0 };
}

/** How well an overlay fits the viewer's side: their own side, then neutral, then the other side. */
function sideRank(o: Overlay, side: Overlay["side"]): number {
  return o.side === side ? 2 : o.side === "neutral" ? 1 : 0;
}

const langRank = (o: Overlay, lang: string) => (o.lang === lang ? 2 : o.lang === "en-GB" ? 1 : 0);

/**
 * One overlay per moment for the chosen lens. Language matters most (a moment not yet in the
 * caption language falls back to en-GB), then side, then surface: a home viewer gets the home
 * telling on any surface before a neutral one on the right surface.
 */
export function selectOverlays(
  all: Overlay[],
  surface: Overlay["surface"],
  lens: Overlay["lens"],
  side: Overlay["side"] = "neutral",
  lang = "en-GB",
): Overlay[] {
  const rank = (o: Overlay) => langRank(o, lang) * 6 + sideRank(o, side) * 2 + (o.surface === surface ? 1 : 0);
  const byMoment = new Map<number, Overlay>();
  for (const o of all) {
    if (o.lens !== lens || o.approval.state === "rejected" || o.approval.state === "pending") continue;
    const cur = byMoment.get(o.match_tc);
    if (!cur || rank(o) > rank(cur)) byMoment.set(o.match_tc, o);
  }
  return [...byMoment.values()];
}

/** Wall-clock ms at which each breakdown starts, and the loop length (for scrubbing and chapters). */
export function timeline(matchEndMs: number, overlays: Overlay[]): { starts: { overlay: Overlay; at: number }[]; loopMs: number } {
  const sorted = overlays.filter((o) => o.match_tc <= matchEndMs).sort((a, b) => a.match_tc - b.match_tc);
  let wall = 0;
  let cursor = 0;
  const starts = sorted.map((o) => {
    wall += o.match_tc - cursor;
    cursor = o.match_tc;
    const at = wall;
    wall += breakdownDurationMs(o);
    return { overlay: o, at };
  });
  return { starts, loopMs: wall + (matchEndMs - cursor) };
}
