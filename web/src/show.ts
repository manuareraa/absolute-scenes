// Post-match show playback: a `show` contract from `chalktalk_postmatch` plays as chapters. Each
// chapter runs a few seconds of play up to its moment, then holds there for the breakdown.
import type { EvidenceMap } from "./evidence";
import type { Frame, Overlay, Show } from "@chalktalk/contracts";
import { breakdownDurationMs, type PlayState } from "./playback";

/** Built by `web/scripts/show_fixture.py`: frames are only the windows round each moment. */
export interface ShowFixture {
  match_id: string;
  fps: number;
  frames: Frame[];
  shows: Show[];
  /** Each claim's evidence replay, by output hash (`evidence.ts`). */
  evidence?: EvidenceMap;
}

/** Play before each moment; the fixture keeps 4 s of frames before every match_tc. */
export const PRE_ROLL_MS = 4000;

export interface Chapter {
  title: string;
  overlay: Overlay;
  /** Wall ms where the chapter (its pre-roll) starts. */
  at: number;
  preRollMs: number;
  breakdownMs: number;
}

export interface ShowState extends PlayState {
  chapter: number;
}

/**
 * Overlays with `script.audio_url` resolved against `base` (the folder the crew's `audio/` sits
 * in). A segment's own `audio_url` wins over the script's.
 */
export function chaptersOf(show: Show, base: string): { chapters: Chapter[]; totalMs: number } {
  let at = 0;
  const chapters = show.segments.map((seg) => {
    const url = seg.audio_url ?? seg.overlay.script.audio_url;
    const overlay: Overlay = url ? { ...seg.overlay, script: { ...seg.overlay.script, audio_url: new URL(url, base).href } } : seg.overlay;
    const preRollMs = Math.min(PRE_ROLL_MS, overlay.match_tc);
    const ch = { title: seg.chapter_title, overlay, at, preRollMs, breakdownMs: breakdownDurationMs(overlay) };
    at += preRollMs + ch.breakdownMs;
    return ch;
  });
  return { chapters, totalMs: at };
}

/** Where the show is after `elapsedMs` of wall time, looping. */
export function showStateAt(chapters: Chapter[], totalMs: number, elapsedMs: number): ShowState {
  if (!chapters.length || totalMs <= 0) return { chapter: -1, matchT: 0, overlay: null, audioMs: 0 };
  const e = ((elapsedMs % totalMs) + totalMs) % totalMs;
  let i = chapters.length - 1;
  while (i > 0 && chapters[i].at > e) i--;
  const ch = chapters[i];
  const into = e - ch.at;
  if (into < ch.preRollMs) return { chapter: i, matchT: ch.overlay.match_tc - ch.preRollMs + into, overlay: null, audioMs: 0 };
  return { chapter: i, matchT: ch.overlay.match_tc, overlay: ch.overlay, audioMs: into - ch.preRollMs };
}

/** The show for this lens and side, else the same lens on any side, else the first. */
export function pickShow(shows: Show[], lens: Show["lens"], side: Show["side"]): Show | undefined {
  return shows.find((s) => s.lens === lens && s.side === side) ?? shows.find((s) => s.lens === lens) ?? shows[0];
}
