import { useEffect, useMemo, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { PitchView } from "./components/PitchView";
import { applyHubMessage, liveMatchT, newLiveState } from "./live";
import { breakdownDurationMs, frameAt } from "./playback";
import {
  applyDecisions,
  approvalFor,
  counts,
  gatePassed,
  gateRows,
  isOpen,
  loadDecisions,
  mergeQueue,
  momentTellings,
  postDecision,
  restartMatch,
  withdrawn,
  queueOrder,
  saveDecisions,
  type Approval,
  type Decision,
  type QueueFixture,
} from "./producer";
import { keepConnected, matchWsUrl } from "./ws";

/** `/producer?queue=queue-sim-7`; the page sits behind Cloudflare Access once deployed. */
const QUEUE_ID = new URLSearchParams(location.search).get("queue") ?? "queue-sim-7";

export function Producer() {
  const [fx, setFx] = useState<QueueFixture | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Approval>>({});
  const [openOnly, setOpenOnly] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [by, setBy] = useState("producer");
  // The hub secret stays in memory only: never stored, never in the URL.
  const [secret, setSecret] = useState("");
  const [sent, setSent] = useState<Record<string, string>>({});
  // The live match on the hub: its clock (to see what is about to air) and the crew's posts.
  const hub = useRef(newLiveState());
  const [hubUp, setHubUp] = useState(false);
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
      onMode: (m) => setHubUp(m === "live"),
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
  const queue = useMemo(() => queueOrder(all, openOnly), [all, openOnly]);
  const current = all.find((o) => o.id === selected) ?? queue[0] ?? null;
  const tally = counts(all);

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
    setSelected(queueOrder(applyDecisions(all, next), true).find((q) => !ids.has(q.id))?.id ?? null);
    if (!secret) return;
    for (const x of batch) setSent((s) => ({ ...s, [x.id]: "sending…" }));
    const results = await Promise.all(
      batch.map((x) => postDecision(fetch, fx.match_id, { ...x, approval: next[x.id] }, secret).catch(() => ({ ok: false, status: 0 }))),
    );
    const bad = results.find((r) => !r.ok);
    const msg = bad ? `hub said ${bad.status || "unreachable"}` : batch.length > 1 ? `${batch.length} tellings sent to hub` : "sent to hub";
    for (const x of batch) setSent((s) => ({ ...s, [x.id]: msg }));
  }

  /** A new take: withdraw this console's approvals from the hub, clear them, and restart the
   * match from kick-off, so nothing airs until it is approved again. */
  async function onRestart() {
    if (!fx || !secret) return;
    setRestart("restarting…");
    const aired = all.filter((o) => decisions[o.id]?.state === "approved" || decisions[o.id]?.state === "overridden");
    const fail = { ok: false, status: 0 };
    const pulled = await Promise.all(aired.map((o) => postDecision(fetch, fx.match_id, withdrawn(o), secret).catch(() => fail)));
    const bad = pulled.find((r) => !r.ok);
    if (bad) return setRestart(`hub said ${bad.status || "unreachable"}`);
    setDecisions({});
    saveDecisions(fx.match_id, {});
    setSent({});
    const r = await restartMatch(fetch, fx.match_id, secret).catch(() => fail);
    setRestart(r.ok ? "" : `hub said ${r.status || "unreachable"}`);
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

  return (
    <main className="app producer">
      <header className="bar">
        <h1>ChalkTalk · Producer</h1>
        <span className="badge">{fx?.match_id ?? "loading…"}</span>
        <span className="tally">
          {tally.pending} pending · {tally.approved} approved · {tally.overridden} overridden · {tally.rejected} rejected
        </span>
        <label className="field">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Pending only
        </label>
        <label className="field">
          By <input value={by} onChange={(e) => setBy(e.target.value)} size={10} />
        </label>
        <label className="field" title="Optional: decisions are also posted to the match hub">
          Hub secret <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} size={10} autoComplete="off" />
        </label>
        <span className={`badge ${hubUp ? "live" : "fixture"}`} title="The match clock on the hub">
          {hubUp && liveT !== null ? `live ${clock(liveT)}` : "hub offline"}
        </span>
        {hubUp && (
          <button disabled={!secret} title={secret ? "New take: withdraw approvals, back to kick-off, playing" : "Enter the hub secret first"} onClick={() => void onRestart()}>
            Restart match
          </button>
        )}
        {restart && <span className="sent">{restart}</span>}
      </header>

      <div className="stage">
        <nav className="queue" aria-label="Queue">
          {queue.map((o) => (
            <button key={o.id} className={o.id === current?.id ? "on" : ""} onClick={() => setSelected(o.id)}>
              <b>{minute(o.match_tc)}</b> {o.lens} · {o.side} · {o.lang}
              {liveT !== null && isOpen(o) && <span className="state">{airing(o.match_tc, liveT)}</span>}
              <span className={`state ${o.approval.state}`}>{o.approval.state}</span>
              {!gatePassed(o) && <span className="state rejected">gate failed</span>}
            </button>
          ))}
          {!queue.length && <p className="empty">Nothing waiting.</p>}
        </nav>

        {current && (
          <section className="review" aria-label="Review">
            <div className="screen">
              <PitchView frame={frameAt(fx?.frames ?? [], current.match_tc)}>
                <OverlayLayer overlay={current} frame={frameAt(fx?.frames ?? [], current.match_tc)} audioMs={breakdownDurationMs(current)} />
              </PitchView>
            </div>
            <p className="script">{current.script.text}</p>
            <div className="facts">
              <table>
                <caption>Gate {gatePassed(current) ? "passed" : "failed"}</caption>
                <tbody>
                  {gateRows(current).map((g) => (
                    <tr key={g.name}>
                      <td>{g.name.replaceAll("_", " ")}</td>
                      <td>{g.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table>
                <caption>Claims</caption>
                <tbody>
                  {current.claims.map((c) => (
                    <tr key={c.id}>
                      <td>{c.tool_call.name}</td>
                      <td>
                        {String(c.value)} {c.unit ?? ""}
                      </td>
                      <td>{c.verified ? "verified" : "unverified"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="actions">
              {isOpen(current) ? (
                <>
                  <button className="approve" onClick={() => void decide(current, "approve")}>
                    {gatePassed(current) ? "Approve" : "Override and approve"} <kbd>a</kbd>
                  </button>
                  {momentTellings(all, current).length > 1 && (
                    <button className="approve" title="Every lens, side and language of this moment" onClick={() => void decide(current, "approve", true)}>
                      Approve the moment ({momentTellings(all, current).length}) <kbd>m</kbd>
                    </button>
                  )}
                  <button className="reject" onClick={() => void decide(current, "reject")}>
                    Reject <kbd>r</kbd>
                  </button>
                </>
              ) : (
                <>
                  <span className={`state ${current.approval.state}`}>
                    {current.approval.state} by {current.approval.by ?? "—"}
                  </span>
                  {decisions[current.id] && <button onClick={() => undo(current)}>Undo</button>}
                </>
              )}
              {sent[current.id] && <span className="sent">{sent[current.id]}</span>}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

const clock = (ms: number) => `${String(Math.floor(ms / 60_000)).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

/** "airs in 12 s" while the moment is ahead of the live clock, "aired" after. */
function airing(t: number, liveT: number): string {
  return t > liveT ? `airs in ${Math.ceil((t - liveT) / 1000)} s` : "aired";
}

function minute(ms: number): string {
  return `${Math.floor(ms / 60_000) + 1}'`;
}
