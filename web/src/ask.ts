// "Ask the pundit": the viewer's side of POST /api/ask. The live crew streams NDJSON
// (contracts/schemas/ask-event.schema.json): who is thinking, which tool ran, which claims were
// rejected and rewritten, then one overlay that plays like a show chapter. Without the backend a
// rehearsal feed (public/fixtures/ask/*.ndjson) replays the same events at their recorded pace.
import type { AskEvent as WireEvent, Overlay } from "@chalktalk/contracts";
import { geometryOverlay } from "./evidence";

// From the generated contract; the overlay keeps the shared Overlay type the player already plays.
export type AskEvent = Omit<WireEvent, "overlay"> & { overlay?: Overlay };
export type Agent = NonNullable<WireEvent["agent"]>;
export type ToolRun = NonNullable<WireEvent["tool"]>;
export type Verdict = NonNullable<WireEvent["verdict"]>;
export type Counterfactual = NonNullable<WireEvent["counterfactual"]>;
export type Metric = Counterfactual["metrics"][number];

/** The body of POST /api/ask. */
export interface AskRequest {
  question: string;
  /** Which suggested question, when the viewer tapped one. */
  suggestion?: SuggestionKey;
  match_id: string;
  /** The overlay on screen when the viewer paused, if any. */
  moment_id?: string;
  match_tc: number;
  lang: string;
  lens: Overlay["lens"];
  side: Overlay["side"];
}

export type AskSource = "live" | "rehearsal";
export const SUGGESTION_KEYS = ["counterfactual", "space", "chance", "offside", "press", "key_player"] as const;
export type SuggestionKey = (typeof SUGGESTION_KEYS)[number];

/** Reads an NDJSON body line by line; a torn last line waits for the next chunk. */
export async function* readNdjson(body: ReadableStream<Uint8Array>, signal?: AbortSignal): AsyncGenerator<AskEvent> {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      buf += done ? dec.decode() : dec.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) yield JSON.parse(line) as AskEvent;
      }
      if (done) break;
    }
    if (buf.trim()) yield JSON.parse(buf) as AskEvent;
  } finally {
    reader.releaseLock();
  }
}

/** Thrown when /api/ask is not there (no backend yet, or switched off). */
export class AskUnavailable extends Error {
  constructor(readonly status: number) {
    super(`ask unavailable (${status})`);
  }
}

/** The live crew's stream. 404 and 501 mean there is no backend behind the route yet. */
export async function* liveAsk(req: AskRequest, signal: AbortSignal, fetchFn: typeof fetch = fetch): AsyncGenerator<AskEvent> {
  let res: Response;
  try {
    res = await fetchFn("/api/ask", { method: "POST", headers: { "content-type": "application/json", accept: "application/x-ndjson" }, body: JSON.stringify(req), signal });
  } catch (e) {
    if (signal.aborted) return;
    throw new AskUnavailable(0);
  }
  if (res.status === 404 || res.status === 501) throw new AskUnavailable(res.status);
  if (!res.ok || !res.body) {
    // 429 (rate limit or daily quota) and 503 (switched off) carry a reason for the viewer.
    const reason = await res.text().catch(() => "");
    yield { type: "error", seq: 0, t_ms: 0, text: errorText(res.status, reason) };
    return;
  }
  yield* readNdjson(res.body, signal);
}

function errorText(status: number, body: string): string {
  try {
    const j = JSON.parse(body) as { error?: string };
    if (j.error) return j.error;
  } catch {
    // Not JSON: fall through to the status code.
  }
  return status === 429 ? "busy" : status === 503 ? "off" : `http ${status}`;
}

export interface FeedEntry {
  key: SuggestionKey;
  match_id: string;
  match_tc: number;
  lang: string;
  file: string;
}

/** Picks the rehearsal feed for a request: same question and language, nearest moment. */
export function pickFeed(feeds: FeedEntry[], req: AskRequest): FeedEntry | undefined {
  const base = req.lang.split("-")[0];
  const fit = feeds.filter((f) => f.key === req.suggestion && f.match_id === req.match_id);
  const lang = fit.filter((f) => f.lang === req.lang);
  const near = (fs: FeedEntry[]) => [...fs].sort((a, b) => Math.abs(a.match_tc - req.match_tc) - Math.abs(b.match_tc - req.match_tc))[0];
  return near(lang) ?? near(fit.filter((f) => f.lang.split("-")[0] === base)) ?? near(fit.filter((f) => f.lang === "en-GB"));
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (ms <= 0 || signal.aborted) return resolve();
    const id = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(id), resolve()), { once: true });
  });

/**
 * The rehearsal feed: replays a recorded stream at its own `t_ms` pace (`speed` 0 = no waits).
 * A question with no recorded answer gets an honest refusal instead of a made-up one.
 */
export async function* fakeAsk(req: AskRequest, signal: AbortSignal, opts: { base?: string; speed?: number; fetchFn?: typeof fetch } = {}): AsyncGenerator<AskEvent> {
  const base = opts.base ?? "/fixtures/ask/";
  const speed = opts.speed ?? 1;
  const get = opts.fetchFn ?? fetch;
  const idx = (await get(`${base}index.json`, { signal }).then((r) => r.json())) as { feeds: FeedEntry[] };
  const feed = pickFeed(idx.feeds, req);
  if (!feed) {
    await wait(400 * speed, signal);
    yield { type: "step", seq: 0, t_ms: 0, agent: "director", text: req.question.slice(0, 400) };
    await wait(500 * speed, signal);
    yield { type: "refusal", seq: 1, t_ms: 900, agent: "director", text: "rehearsal" };
    yield { type: "done", seq: 2, t_ms: 900 };
    return;
  }
  const res = await get(base + feed.file, { signal });
  let last = 0;
  for await (const ev of readNdjson(res.body!, signal)) {
    await wait((ev.t_ms - last) * speed, signal);
    if (signal.aborted) return;
    last = ev.t_ms;
    yield ev;
  }
}

// ---- What the strip and the screen show, folded from the events in order. ----

export type Phase = "idle" | "thinking" | "answering" | "done" | "refused" | "error";

export type Row =
  | { kind: "step"; seq: number; agent: Agent; text: string }
  | { kind: "tool"; seq: number; agent: Agent; tool: ToolRun }
  | { kind: "verdict"; seq: number; agent: Agent; verdict: Verdict; superseded: boolean }
  | { kind: "counterfactual"; seq: number; agent: Agent; cf: Counterfactual };

export interface StudioState {
  phase: Phase;
  question: string;
  source: AskSource;
  rows: Row[];
  /** Who is working now: the agent of the latest step, until the answer airs. */
  active: Agent | null;
  overlay: Overlay | null;
  /** The change the ghosts show: the accepted proposal, else the last one tested. */
  counterfactual: Counterfactual | null;
  /** refusal/error reason. */
  message: string | null;
  cached: boolean;
  traceId: string | null;
  /** The tools' geometry so far, drawn at once while the crew thinks; the answer replaces it. */
  sketch: Overlay | null;
}

export const idleStudio: StudioState = { phase: "idle", question: "", source: "live", rows: [], active: null, overlay: null, counterfactual: null, message: null, cached: false, traceId: null, sketch: null };

export function startStudio(question: string, source: AskSource): StudioState {
  return { ...idleStudio, phase: "thinking", question, source };
}

export function studioReduce(st: StudioState, ev: AskEvent): StudioState {
  const agent: Agent = ev.agent ?? "director";
  switch (ev.type) {
    case "step":
      return { ...st, active: agent, rows: [...st.rows, { kind: "step", seq: ev.seq, agent, text: ev.text ?? "" }] };
    case "tool": {
      if (!ev.tool) return st;
      const sk = ev.tool.sketch;
      const sketch = sk ? geometryOverlay([...(st.sketch?.match_tc === sk.match_tc ? st.sketch.strokes : []), ...sk.strokes], sk.match_tc, "ask-sketch") : st.sketch;
      return { ...st, active: agent, sketch, rows: [...st.rows, { kind: "tool", seq: ev.seq, agent, tool: ev.tool }] };
    }
    case "verdict": {
      if (!ev.verdict) return st;
      // A new round supersedes the rejected claims of earlier rounds: they stay, struck through.
      const v = ev.verdict;
      const rows = st.rows.map((r) => (r.kind === "verdict" && !r.verdict.ok && r.verdict.round < v.round ? { ...r, superseded: true } : r));
      return { ...st, active: agent, rows: [...rows, { kind: "verdict", seq: ev.seq, agent, verdict: v, superseded: false }] };
    }
    case "counterfactual": {
      if (!ev.counterfactual) return st;
      const cf = ev.counterfactual;
      const keep = st.counterfactual?.accepted && !cf.accepted ? st.counterfactual : cf;
      return { ...st, active: agent, counterfactual: keep, rows: [...st.rows, { kind: "counterfactual", seq: ev.seq, agent, cf }] };
    }
    case "overlay": {
      if (!ev.overlay) return st;
      const overlay = ev.audio_url ? { ...ev.overlay, script: { ...ev.overlay.script, audio_url: ev.audio_url } } : ev.overlay;
      return { ...st, phase: "answering", active: "pundit", overlay };
    }
    case "refusal":
      return { ...st, phase: "refused", active: null, message: ev.text ?? "" };
    case "error":
      return { ...st, phase: "error", active: null, message: ev.text ?? "" };
    case "done":
      return { ...st, phase: st.phase === "thinking" ? (st.overlay ? "answering" : "error") : st.phase, active: st.overlay ? st.active : null, cached: ev.cached ?? false, traceId: ev.trace_id ?? null };
  }
}

/** When an answer overlay has finished speaking: its last word, plus a beat for the last stroke. */
export function answerEndMs(o: Overlay): number {
  const words = o.script.words ?? [];
  const lastWord = words.length ? Math.max(...words.map((w) => w.offset_ms + w.duration_ms)) : 0;
  const lastStroke = Math.max(0, ...o.strokes.map((s) => (o.script.cues.find((c) => c.cue_id === s.cue_id)?.offset_ms ?? 0) + (s.duration_ms ?? 600)));
  return Math.max(lastWord, lastStroke) + 800;
}

/** Moment-specific questions, by the claims the moment's overlay makes. */
const BY_SLOT: [RegExp, SuggestionKey][] = [
  [/offside|var/i, "offside"],
  [/xg/i, "chance"],
  [/gap|line/i, "space"],
  [/press/i, "press"],
];

/** The moment's three suggested questions; "What should they have done?" is always first. */
export function suggestionsFor(overlay: Overlay | null): SuggestionKey[] {
  const slots = (overlay?.claims ?? []).map((c) => c.text_slot).join(" ") + " " + (overlay?.id ?? "");
  const hit = BY_SLOT.find(([re]) => re.test(slots))?.[1] ?? "space";
  return ["counterfactual", hit, "key_player"];
}

/**
 * `?ask=fake` forces the rehearsal feed and `?ask=live` the backend only. By default the live crew
 * answers and, while /api/ask has no backend behind it, the rehearsal feed stands in, labelled.
 */
export function askMode(params: URLSearchParams): "live" | "rehearsal" | "auto" {
  const p = params.get("ask");
  if (p === "fake" || p === "rehearsal") return "rehearsal";
  if (p === "live") return "live";
  return "auto";
}
