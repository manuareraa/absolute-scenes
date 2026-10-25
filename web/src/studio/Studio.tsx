// The studio around "Ask the pundit": the ask bar under the pitch, the control-room strip beside
// it, and the before/after chips for the change the ghosts show.
import { useEffect, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import type { Agent, Counterfactual, Metric, Row, StudioState, SuggestionKey } from "../ask";
import { num, type Strings } from "../i18n";
import { listen, canRecord, type Listening, type VoiceProblem } from "./voice";
import "./studio.css";

const AGENTS: Agent[] = ["director", "analyst", "tactician", "critic", "pundit", "verifier"];

export function AskBar(props: {
  s: Strings;
  lang: string;
  suggestions: SuggestionKey[];
  busy: boolean;
  /** The viewer went to the bar: pause the show. */
  onPause(): void;
  /** The viewer typed or spoke again: stop the answer on screen. */
  onBargeIn(): void;
  onAsk(question: string, key?: SuggestionKey): void;
  onStop(): void;
}) {
  const { s, lang } = props;
  const t = s.ask;
  const [text, setText] = useState("");
  const [mic, setMic] = useState<"idle" | "listening" | VoiceProblem>(canRecord() ? "idle" : "unavailable");
  const listening = useRef<Listening | null>(null);
  useEffect(() => () => listening.current?.stop(), []);

  const submit = (q: string, key?: SuggestionKey) => {
    const question = q.trim();
    if (!question) return;
    listening.current?.stop();
    props.onAsk(question, key);
    setText("");
  };
  const toggleMic = async () => {
    if (mic === "listening") return listening.current?.stop();
    setMic("listening");
    listening.current = await listen(lang, {
      onSpeech: () => {
        props.onPause();
        props.onBargeIn();
      },
      onPartial: setText,
      onFinal: (q) => submit(q),
      onEnd: (p) => {
        listening.current = null;
        setMic(p ?? "idle");
      },
    });
  };
  const micDown = mic === "unavailable" || mic === "denied";
  const micTitle = mic === "unavailable" ? t.micOff : mic === "denied" ? t.micDenied : mic === "listening" ? t.listening : t.mic;

  return (
    <form
      className="ask-bar"
      aria-label={t.title}
      onSubmit={(e) => {
        e.preventDefault();
        submit(text);
      }}
    >
      <div className="ask-row">
        <span className="ask-tag" aria-hidden>
          {t.title}
        </span>
        <input
          className="ask-input"
          value={text}
          placeholder={mic === "listening" ? t.listening : t.placeholder}
          aria-label={t.placeholder}
          title={t.pauses}
          maxLength={300}
          onFocus={props.onPause}
          onChange={(e) => {
            setText(e.target.value);
            props.onBargeIn();
          }}
          onKeyDown={(e) => e.key === "Escape" && (e.currentTarget.blur(), setText(""))}
        />
        <button type="button" className={`ask-mic ${mic}`} onClick={toggleMic} disabled={micDown} aria-pressed={mic === "listening"} aria-label={micTitle} title={micTitle}>
          <MicIcon />
        </button>
        {props.busy ? (
          <button type="button" className="ask-send stop" onClick={props.onStop}>
            {t.stop}
          </button>
        ) : (
          <button type="submit" className="ask-send" disabled={!text.trim()}>
            {t.send}
          </button>
        )}
      </div>
      <div className="ask-suggest">
        {props.suggestions.map((k) => (
          <button type="button" key={k} onClick={() => submit(t.suggestions[k], k)}>
            {t.suggestions[k]}
          </button>
        ))}
      </div>
    </form>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

/** The broadcast gallery: tally lights for each agent, then the run as it happens. */
export function ControlRoom(props: { st: StudioState; s: Strings; lang: string; onBack(): void }) {
  const { st, s, lang } = props;
  const t = s.ask;
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [st.rows.length, st.phase]);
  const name = (a: Agent) => t.agents[a] ?? a;
  const onAir = st.phase === "answering";
  const status = st.phase === "thinking" && st.active ? t.working(name(st.active)) : onAir ? t.onAir : st.phase === "refused" || st.phase === "error" ? "" : t.standby;
  const message = st.phase === "refused" ? (t.refusals[st.message ?? ""] ?? (st.message || t.refusals.default)) : st.phase === "error" ? (t.errors[st.message ?? ""] ?? t.errors.default) : null;

  return (
    <aside className={`control-room phase-${st.phase}`} aria-label={t.controlRoom} aria-live="polite">
      <header className="cr-head">
        <h2>{t.controlRoom}</h2>
        <span className={`cr-source ${st.source}`} title={st.source === "rehearsal" ? t.rehearsalHint : undefined}>
          {st.source === "rehearsal" ? t.rehearsal : t.live}
        </span>
      </header>
      <ul className="cr-tally" aria-hidden>
        {AGENTS.map((a) => (
          <li key={a} className={`${a}${st.active === a ? " on" : ""}${st.rows.some((r) => r.agent === a) ? " used" : ""}`}>
            {name(a)}
          </li>
        ))}
      </ul>
      <p className="cr-question">
        <small>{t.youAsked}</small> {st.question}
      </p>
      <ol className="cr-rows" ref={list}>
        {st.rows.map((r) => (
          <RowView key={r.seq} r={r} s={s} lang={lang} name={name(r.agent)} />
        ))}
      </ol>
      <footer className="cr-foot">
        {message ? (
          <p className="cr-message" role="status">
            {message}
          </p>
        ) : (
          <p className={`cr-status${onAir ? " on-air" : ""}${st.phase === "thinking" ? " busy" : ""}`}>
            {status}
            {st.cached && st.phase !== "thinking" && <small> · {t.cached}</small>}
          </p>
        )}
        <button className="cr-back" onClick={props.onBack}>
          {t.back}
        </button>
      </footer>
    </aside>
  );
}

function RowView({ r, s, lang, name }: { r: Row; s: Strings; lang: string; name: string }) {
  const t = s.ask;
  const who = <b className={`cr-agent ${r.agent}`}>{name}</b>;
  switch (r.kind) {
    case "step":
      return (
        <li className="cr-row step">
          {who}
          <span>{r.text}</span>
        </li>
      );
    case "tool":
      return (
        <li className="cr-row tool">
          {who}
          <span>
            <code>{r.tool.name}</code>
            {r.tool.ms !== undefined && <small className="cr-ms">{r.tool.ms} ms</small>}
            <br />
            {r.tool.summary}
          </span>
        </li>
      );
    case "verdict":
      return (
        <li className={`cr-row verdict ${r.verdict.ok ? "ok" : "rejected"}${r.superseded ? " superseded" : ""}`}>
          {who}
          <span>
            <small className="cr-flag">
              {r.verdict.ok ? t.approved : t.rejected} · {t.round(r.verdict.round)}
            </small>
            <q>{r.verdict.claim}</q>
            {r.verdict.reason && <em>{r.verdict.reason}</em>}
          </span>
        </li>
      );
    case "counterfactual":
      return (
        <li className={`cr-row cf ${r.cf.accepted ? "ok" : "rejected"}`}>
          {who}
          <span>
            <small className="cr-flag">{r.cf.accepted ? t.helps : t.noHelp}</small>
            {r.cf.proposal}
            <span className="cr-metrics">
              {r.cf.metrics.map((m) => (
                <MetricChip key={m.name} m={m} s={s} lang={lang} />
              ))}
            </span>
          </span>
        </li>
      );
  }
}

const unitOf = (name: string) => (/_m$/.test(name) ? " m" : /_pts$/.test(name) ? " pts" : /_pct$|_box$/.test(name) ? "%" : "");
const signed = (v: number, name: string, lang: string) => (/_pts$/.test(name) && v > 0 ? "+" : "") + num(v, lang).replace("-", "−");

export function MetricChip({ m, s, lang }: { m: Metric; s: Strings; lang: string }) {
  const u = unitOf(m.name);
  return (
    <span className="metric-chip" title={m.tool_call}>
      <small>{s.ask.metrics[m.name] ?? m.name.replaceAll("_", " ")}</small>
      <span className="before" aria-label={s.ask.before}>
        {signed(m.before, m.name, lang)}
        {u}
      </span>
      <span aria-hidden>→</span>
      <b className="after" aria-label={s.ask.after}>
        {signed(m.after, m.name, lang)}
        {u}
      </b>
    </span>
  );
}

/** When the answer's ghosts start drawing: the first ghost_path stroke's start on the audio clock. */
export function ghostStartMs(o: Overlay): number | null {
  const g = o.strokes.find((x) => x.shape === "ghost_path");
  if (!g) return null;
  const cue = o.script.cues.find((c) => c.cue_id === g.cue_id);
  return cue ? cue.offset_ms - (g.lead_ms ?? 150) : null;
}

/** The before/after chips for the change the ghosts show, once the ghosts are on the pitch. */
export function WhatIf({ cf, overlay, audioMs, s, lang }: { cf: Counterfactual; overlay: Overlay; audioMs: number; s: Strings; lang: string }) {
  const at = ghostStartMs(overlay);
  if (at === null || audioMs < at) return null;
  return (
    <div className={`what-if ${cf.accepted ? "ok" : "rejected"}`} role="status">
      <p>
        <small>{s.ask.tried}</small> {cf.proposal}
      </p>
      <div className="what-if-chips">
        {cf.metrics.map((m) => (
          <MetricChip key={m.name} m={m} s={s} lang={lang} />
        ))}
      </div>
      <p className="what-if-verdict">{cf.accepted ? s.ask.helps : s.ask.noHelp}</p>
    </div>
  );
}
