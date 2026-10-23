// Evidence replay (M9): tap a number in the caption, or a claim chip, and the pitch replays the
// window that number came from, with the tool's own geometry fully drawn. Entries are built by
// `web/scripts/show_fixture.py` from B's `evidence` tool, keyed by the claim's output hash.
import type { Frame, Overlay } from "@chalktalk/contracts";

type Claim = Overlay["claims"][number];
type Stroke = Overlay["strokes"][number];

export interface EvidenceEntry {
  tool: string;
  args: Record<string, unknown>;
  claim_value: unknown;
  unit: string | null;
  /** `match`: the re-run agrees (hash, or value within tolerance); `differs`: it does not;
   * `window`: the tool cannot be re-run here, so this replays the claim's own window. */
  check: "match" | "differs" | "window";
  rerun_value: unknown;
  hash_match: boolean | null;
  replay: { start_t: number; end_t: number };
  geometry: Pick<Stroke, "shape" | "geometry_m" | "style">[];
  events: { t: number; type: string; team?: string; actors?: string[] }[];
}

export type EvidenceMap = Record<string, EvidenceEntry>;

export const evidenceFor = (map: EvidenceMap | undefined, c: Claim) => map?.[c.tool_call.output_hash];

/** Words after which a number is a shirt number, not a measurement ("number 9", "el dorsal 9"). */
const SHIRT = new Set(["number", "no", "número", "numero", "dorsal"]);

/** How far a caption word's numbers are from a claim's value, if it could be speaking it: the same
 * value to the number's precision, or within the claim's tolerance. Speech word timings can join
 * tokens ("9 is 4.6"), so every number in the word counts except a shirt number. The decimal may be
 * a comma (es-ES says "14,4"); a trailing comma is punctuation. `prev` is the word before. */
function wordDistance(c: Claim, word: string, prev = ""): number | null {
  const v = Number(c.value);
  if (!Number.isFinite(v)) return null;
  const tokens = [prev.split(/\s+/).pop() ?? "", ...word.split(/\s+/)];
  let best: number | null = null;
  for (let i = 1; i < tokens.length; i++) {
    const m = tokens[i].match(/^-?\d+(?:[.,](\d+))?/);
    if (!m || SHIRT.has(tokens[i - 1].toLowerCase().replace(/[^\p{L}]/gu, ""))) continue;
    const d = Math.abs(v - Number(m[0].replace(",", ".")));
    const half = 0.5 * 10 ** -(m[1]?.length ?? 0) + 1e-9;
    if ((d <= half || d <= (c.tolerance ?? 0)) && (best === null || d < best)) best = d;
  }
  return best;
}

/** The claim a caption word speaks, if it is a number. */
export function claimForWord(overlay: Overlay, word: string, prev = ""): Claim | undefined {
  return overlay.claims.find((c) => wordDistance(c, word, prev) !== null);
}

/** Word index -> the claim it speaks: each claim on its closest word, and never on a shirt number,
 * so "number 7" is not mistaken for "7.1 metres". */
export function claimWords(overlay: Overlay): Map<number, Claim> {
  const words = overlay.script.words ?? [];
  const out = new Map<number, Claim>();
  for (const c of overlay.claims) {
    let best = -1;
    let bestD = Infinity;
    words.forEach((w, i) => {
      const d = wordDistance(c, w.text, words[i - 1]?.text);
      if (d !== null && d < bestD && !out.has(i)) [best, bestD] = [i, d];
    });
    if (best >= 0) out.set(best, c);
  }
  return out;
}

/** Hold the last frame this long before the replay loops. */
export const REPLAY_HOLD_MS = 1500;

/** Match time `ms` into a looping replay of the entry's window. */
export function replayMatchT(e: EvidenceEntry, ms: number): number {
  const len = e.replay.end_t - e.replay.start_t;
  const pos = ((ms % (len + REPLAY_HOLD_MS)) + len + REPLAY_HOLD_MS) % (len + REPLAY_HOLD_MS);
  return e.replay.start_t + Math.min(len, pos);
}

/** The evidence as an overlay whose strokes are all drawn at once (no script to wait for). */
export const evidenceOverlay = (e: EvidenceEntry, id: string) => geometryOverlay(e.geometry, e.replay.end_t, `evidence-${id}`);

/** Tool geometry as an overlay at match time `t`, every stroke drawn at once. */
export function geometryOverlay(geometry: EvidenceEntry["geometry"], t: number, id: string): Overlay {
  return {
    id,
    stream_tc: null,
    match_tc: t,
    surface: "show",
    claims: [],
    strokes: geometry.map((g, i) => ({ ...g, id: `e${i + 1}`, cue_id: "ev", lead_ms: 0, duration_ms: 0, claim_ids: [] })),
    script: { text: "", ssml: "", cues: [{ cue_id: "ev", offset_ms: 0 }], words: [] },
    lens: "analyst",
    side: "neutral",
    lang: "en-GB",
    approval: { state: "auto", by: null, at: null },
  } as Overlay;
}

/** The events up to match time `t` in the replay, latest last. */
export const eventsSoFar = (e: EvidenceEntry, t: number) => e.events.filter((x) => x.t <= t);

/** Frames eased between the two either side of `t` (replay frames are sparse). */
export function frameBetween(frames: Frame[], t: number, maxGapMs = 400): Frame | undefined {
  if (!frames.length) return undefined;
  let lo = 0;
  let hi = frames.length - 1;
  if (t <= frames[0].t) return frames[0];
  if (t >= frames[hi].t) return frames[hi];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = frames[lo];
  const b = frames[hi];
  if (b.t - a.t > maxGapMs || b.t === a.t) return a;
  const k = (t - a.t) / (b.t - a.t);
  const mix = (x: number, y: number) => x + (y - x) * k;
  const next = new Map(b.players.map((p) => [p.id, p]));
  return {
    ...a,
    t,
    ball: { ...a.ball, x: mix(a.ball.x, b.ball.x), y: mix(a.ball.y, b.ball.y) },
    players: a.players.map((p) => {
      const q = next.get(p.id);
      return q ? { ...p, x: mix(p.x, q.x), y: mix(p.y, q.y) } : p;
    }),
  };
}

export function checkLabel(e: EvidenceEntry): string {
  if (e.check === "match") return e.hash_match ? "re-run matches, same hash" : "re-run matches";
  if (e.check === "differs") return `re-run gives ${fmt(e.rerun_value)}`;
  return "evidence window (no re-run)";
}

const fmt = (v: unknown) => (typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v));

/** A claim's slot as words, without its unit suffix: `gap_m` -> "gap", `pass_options` stays. */
export const slotLabel = (slot: string) => {
  const words = slot.replace(/_(m|pct|pts|s|ms|kmh)$/, "").replaceAll("_", " ");
  return SLOT_WORDS[words] ?? words;
};
const SLOT_WORDS: Record<string, string> = { pc: "pitch control" };
