import { useEffect, useMemo, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { PitchView } from "./components/PitchView";
import { applyHubMessage, liveMatchT, newLiveState } from "./live";
import { breakdownDurationMs, frameAt } from "./playback";
import {
  airLabel,
  applyDecisions,
  approvalFor,
  broadcastUrl,
  byMoment,
  counts,
  gatePassed,
  gateRows,
  isOpen,
  loadDecisions,
  mergeQueue,
  momentTellings,
  nextMoment,
  postDecision,
  restartMatch,
  withdrawn,
  queueOrder,
  saveDecisions,
  type AirLabel,
  type Approval,
  type Decision,
  type QueueFixture,
} from "./producer";
import { keepConnected, matchWsUrl } from "./ws";

/** `/producer?queue=queue-sim-7`; open to anyone: decisions air on the live match for every viewer. */
const QUEUE_ID = new URLSearchParams(location.search).get("queue") ?? "queue-sim-7";
const INTRO_KEY = "chalktalk.producer.intro";

type HubState = "connecting" | "live" | "offline";
interface Toast {
  text: string;
  prev: Record<string, Approval | undefined>;
  posted: boolean;
}

export function Producer() {
  const [fx, setFx] = useState<QueueFixture | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Approval>>({});
  const [openOnly, setOpenOnly] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [by, setBy] = useState("producer");
  const [sent, setSent] = useState<Record<string, string>>({});
  // The live match on the hub: its clock (to see what is about to air) and the crew's posts.
  const hub = useRef(newLiveState());
  const [hubState, setHubState] = useState<HubState>("connecting");
  const hubUp = hubState === "live";
  const [intro, setIntro] = useState(() => {
    try {
      return localStorage.getItem(INTRO_KEY) === null;
    } catch {
      return true;
    }
  });
  const [toast, setToast] = useState<Toast | null>(null);
  const [posted, setPosted] = useState<Overlay[]>([]);
  const [liveT, setLiveT] = useState<number | null>(null);
  const [restart, setRestart] = useState("");

  useEffect(() => {
    fetch(`/fixtures/${QUEUE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`queue ${r.status}`))))
      .then((q: QueueFixture) => {
        setFx(q);
        setDecisions(loadDecisions(q.match_id));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!fx) return;
    const close = keepConnected(matchWsUrl(fx.match_id, location), {
      onMode: (m) => setHubState(m === "live" ? "live" : m === "connecting" ? "connecting" : "offline"),
      onMessage: (m) => {
        if (m.type === "overlay") return setPosted((p) => [...p.filter((x) => x.id !== m.overlay.id), m.overlay]);
        hub.current = applyHubMessage(hub.current, m, performance.now());
      },
    });
    const tick = setInterval(() => setLiveT(hub.current.durationMs ? liveMatchT(hub.current, performance.now()) : null), 500);
    return () => {
      clearInterval(tick);
      close();
    };
  }, [fx]);

  const all = useMemo(
    () => (fx ? applyDecisions(mergeQueue(fx.overlays, posted.filter(isOpen)), decisions) : []),
    [fx, posted, decisions],
  );
  const queue = queueOrder(all, openOnly, liveT);
  const groups = byMoment(queue);
  const current = all.find((o) => o.id === selected) ?? queue[0] ?? null;
  const tally = counts(all);
  const next = hubUp && liveT !== null ? nextMoment(all, liveT) : null;

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(t);
  }, [toast]);

  function closeIntro() {
    setIntro(false);
    try {
      localStorage.setItem(INTRO_KEY, "seen");
    } catch {
      // Blocked storage: the panel comes back next visit.
    }
  }

  async function decide(o: Overlay, d: Decision, whole = false) {
    if (!fx) return;
    const at = new Date();
    const batch = whole ? momentTellings(all, o) : [o];
    const next = { ...decisions };
    for (const x of batch) next[x.id] = approvalFor(x, d, by, at);
    setDecisions(next);
    saveDecisions(fx.match_id, next);
    // Move on to the next open overlay.
    const ids = new Set(batch.map((x) => x.id));
    setSelected(queueOrder(applyDecisions(all, next), true, liveT).find((q) => !ids.has(q.id))?.id ?? null);
    const versions = batch.length > 1 ? `${batch.length} versions` : "1 version";
    const text =
      d === "reject"
        ? `Rejected ${versions} of ${clock(o.match_tc)}: it stays off air`
        : `Approved ${versions}: airs at ${clock(o.match_tc)} on the broadcast`;
    setToast({ text, prev: Object.fromEntries(batch.map((x) => [x.id, decisions[x.id]])), posted: true });
    for (const x of batch) setSent((s) => ({ ...s, [x.id]: "sending…" }));
    const results = await Promise.all(
      batch.map((x) => postDecision(fetch, fx.match_id, { ...x, approval: next[x.id] }).catch(() => ({ ok: false, status: 0 }))),
    );
    const bad = results.find((r) => !r.ok);
    const msg = bad ? `hub said ${bad.status || "unreachable"}` : batch.length > 1 ? `${batch.length} tellings sent to hub` : "sent to hub";
    for (const x of batch) setSent((s) => ({ ...s, [x.id]: msg }));
  }

  /** A new take: withdraw this console's approvals from the hub, clear them, and restart the
   * match from kick-off, so nothing airs until it is approved again. */
  async function onRestart() {
    if (!fx) return;
    setRestart("restarting…");
    const aired = all.filter((o) => decisions[o.id]?.state === "approved" || decisions[o.id]?.state === "overridden");
    const fail = { ok: false, status: 0 };
    const pulled = await Promise.all(aired.map((o) => postDecision(fetch, fx.match_id, withdrawn(o)).catch(() => fail)));
    const bad = pulled.find((r) => !r.ok);
    if (bad) return setRestart(`hub said ${bad.status || "unreachable"}`);
    setDecisions({});
    saveDecisions(fx.match_id, {});
    setSent({});
    const r = await restartMatch(fetch, fx.match_id).catch(() => fail);
    setRestart(r.ok ? "" : `hub said ${r.status || "unreachable"}`);
  }

  /** Undo the last decision: restore what each version had before, and pull it off the hub. */
  async function undoToast(t: Toast) {
    if (!fx) return;
    setToast(null);
    const next = { ...decisions };
    for (const [id, prev] of Object.entries(t.prev)) {
      if (prev) next[id] = prev;
      else delete next[id];
    }
    setDecisions(next);
    saveDecisions(fx.match_id, next);
    const first = Object.keys(t.prev)[0];
    if (first) setSelected(first);
    if (!t.posted) return;
    const back = all.filter((o) => o.id in t.prev).map((o) => (t.prev[o.id] ? { ...o, approval: t.prev[o.id]! } : withdrawn(o)));
    await Promise.all(back.map((o) => postDecision(fetch, fx.match_id, o).catch(() => null)));
  }

  function undo(o: Overlay) {
    if (!fx) return;
    const next = { ...decisions };
    delete next[o.id];
    setDecisions(next);
    saveDecisions(fx.match_id, next);
    setSelected(o.id);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!current || !isOpen(current) || e.target instanceof HTMLInputElement) return;
      if (e.key === "a") void decide(current, "approve");
      if (e.key === "m") void decide(current, "approve", true);
      if (e.key === "r") void decide(current, "reject");
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  if (error) return <main className="app error">Could not load the overlay queue: {error}</main>;

  const approvedAll = tally.approved + tally.overridden + tally.auto;
  return (
    <main className="app producer">
      <header className="bar">
        <h1>ChalkTalk · Producer</h1>
        <span className="badge" title="The match this queue belongs to">
          {fx?.match_id ?? "loading…"}
        </span>
        <span className={`badge ${hubUp ? "live" : "fixture"}`} title="The live match clock that viewers are watching" role="status">
          {hubState === "connecting" ? "connecting…" : hubUp && liveT !== null ? `live match ${clock(liveT)}` : "live match offline"}
        </span>
        {hubUp && liveT !== null && (
          <span className="tally" role="status">
            {next !== null ? `Next moment in ${Math.ceil((next - liveT) / 1000)} s` : "No more moments in this match"}
          </span>
        )}
        {hubUp && (
          <button
            title="A new take: withdraw your approvals and play the match again from kick-off, for every viewer"
            onClick={() => void onRestart()}
          >
            Restart match
          </button>
        )}
        {restart && <span className="sent">{restart}</span>}
        <a className="button" href={broadcastUrl(current)} target="_blank" rel="noreferrer" title="The public broadcast in this version's audience, side and language">
          Open broadcast ↗
        </a>
        <button className="icon" onClick={() => setIntro(true)} title="How the producer works" aria-label="How the producer works">
          ?
        </button>
      </header>
      <div className="bar sub">
        {fx && (
          <span className="tally">
            {tally.pending} to review · {approvedAll} approved · {tally.rejected} rejected
          </span>
        )}
        <label className="field" title="Hide the versions you have already decided">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> To review only
        </label>
        <label className="field" title="Recorded with each decision">
          Your name <input value={by} onChange={(e) => setBy(e.target.value)} size={10} />
        </label>
      </div>

      {intro && (
        <section className="intro" aria-labelledby="intro-title">
          <h2 id="intro-title">You are the producer</h2>
          <p>The AI crew writes each pundit moment in many versions (audience, side, language). Nothing reaches viewers until you approve it.</p>
          <ol>
            <li>Pick a moment on the left. Moments that say “airs in” are still ahead of the live match.</li>
            <li>Watch the drawing, read the script, and check the fact-check: every number should trace back to a tracking tool.</li>
            <li>Approve the moment (all its versions) or reject it, then open the broadcast to see it air at its minute.</li>
          </ol>
          <button onClick={closeIntro}>Got it</button>
        </section>
      )}

      <div className="stage">
        <nav className="queue" aria-label="Moments to review">
          {groups.map(({ at, overlays }) => {
            const head = overlays[0];
            const open = momentTellings(all, head);
            return (
              <div key={at} className="moment-group">
                <div className="moment-head">
                  <b>{clock(at)}</b> <span className="title">{head.script.text.split(" ").slice(0, 6).join(" ")}…</span>
                  <AirBadge label={airLabel(head, liveT)} />
                  {open.length > 1 && (
                    <button className="approve-all" title="Approve every version of this moment" onClick={() => void decide(head, "approve", true)}>
                      Approve all {open.length}
                    </button>
                  )}
                </div>
                {overlays.map((o) => (
                  <button key={o.id} className={o.id === current?.id ? "on" : ""} aria-current={o.id === current?.id} onClick={() => setSelected(o.id)}>
                    {o.lens} · {o.side} · {o.lang}
                    <span className={`state ${o.approval.state}`} title={STATE_HINTS[o.approval.state]}>
                      {STATE_WORDS[o.approval.state]}
                    </span>
                    {!gatePassed(o) && <span className="state rejected">fact-check failed</span>}
                  </button>
                ))}
              </div>
            );
          })}
          {fx && !queue.length && <p className="empty">Nothing waiting.</p>}
        </nav>

        {current && (
          <section className="review" aria-label="Review">
            <div className="screen">
              <PitchView frame={frameAt(fx?.frames ?? [], current.match_tc)}>
                <OverlayLayer overlay={current} frame={frameAt(fx?.frames ?? [], current.match_tc)} audioMs={breakdownDurationMs(current)} />
              </PitchView>
            </div>
            <p className="script">{current.script.text}</p>
            <div className="actions">
              {isOpen(current) ? (
                <>
                  <button className="approve" onClick={() => void decide(current, "approve")} title="Approve this version only">
                    {gatePassed(current) ? "Approve" : "Approve anyway"} <kbd>a</kbd>
                  </button>
                  {momentTellings(all, current).length > 1 && (
                    <button className="approve" title="Every audience, side and language of this moment" onClick={() => void decide(current, "approve", true)}>
                      Approve the moment ({momentTellings(all, current).length} versions) <kbd>m</kbd>
                    </button>
                  )}
                  <button className="reject" onClick={() => void decide(current, "reject")} title="Keep this version off air">
                    Reject <kbd>r</kbd>
                  </button>
                </>
              ) : (
                <>
                  <span className={`state ${current.approval.state}`}>
                    {STATE_WORDS[current.approval.state]} by {current.approval.by ?? "—"}
                  </span>
                  {decisions[current.id] && <button onClick={() => undo(current)}>Undo</button>}
                </>
              )}
              {sent[current.id] && <span className="sent">{sent[current.id]}</span>}
            </div>
            <div className="facts">
              <table>
                <caption title="Passed: every number was checked against the tracking tools">
                  Fact-check {gatePassed(current) ? "passed" : "failed"}
                </caption>
                <tbody>
                  {gateRows(current).map((g) => (
                    <tr key={g.name} title={GATE_WORDS[g.name]?.[1]}>
                      <td>{GATE_WORDS[g.name]?.[0] ?? g.name.replaceAll("_", " ")}</td>
                      <td>{g.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table>
                <caption title="Each number in the script and the tool call that produced it">Numbers in the script</caption>
                <tbody>
                  {current.claims.map((c) => (
                    <tr key={c.id}>
                      <td>{c.tool_call.name}</td>
                      <td>
                        {String(c.value)} {c.unit ?? ""}
                      </td>
                      <td>{c.verified ? "checked" : "not checked"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
      {toast && (
        <div className="toast" role="status">
          {toast.text}
          <button onClick={() => void undoToast(toast)}>Undo</button>
        </div>
      )}
    </main>
  );
}

function AirBadge({ label }: { label: AirLabel }) {
  if (!label) return null;
  if (label.kind === "airs-in") return <span className="state">airs in {label.s} s</span>;
  if (label.kind === "aired") return <span className="state approved">aired</span>;
  return (
    <span className="state missed" title="Its minute passed before anyone approved it">
      missed
    </span>
  );
}

const STATE_WORDS: Record<Approval["state"], string> = {
  pending: "to review",
  approved: "approved",
  overridden: "approved anyway",
  rejected: "rejected",
  auto: "auto",
};

const STATE_HINTS: Record<Approval["state"], string> = {
  pending: "Waiting for a producer",
  approved: "Approved: airs at its minute",
  overridden: "Approved although the fact-check failed",
  rejected: "Kept off air",
  auto: "Aired automatically",
};

/** Plain names for the fact-check scores, with what each one measures. */
const GATE_WORDS: Record<string, [string, string]> = {
  claim_verified_rate: ["Numbers checked", "Share of the script's numbers the tracking tools confirmed"],
  cue_integrity: ["Drawings on cue", "Every drawing lands on a word in the script"],
  geometry_from_tools: ["Drawings from tools", "Share of drawings whose coordinates came from a tool, not the model"],
  grounding_rate: ["Backed sentences", "Share of sentences backed by a tool result"],
  hash_match_rate: ["Same match data", "Share of tool results computed on this match's data"],
  template_fallback: ["Template script", "1 when the crew fell back to a template script"],
  unsupported_numbers: ["Unbacked numbers", "Numbers in the script with no tool result behind them"],
};

const clock = (ms: number) => `${String(Math.floor(ms / 60_000)).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;
