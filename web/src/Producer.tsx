import { useEffect, useMemo, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { PitchView } from "./components/PitchView";
import { breakdownDurationMs, frameAt } from "./playback";
import {
  applyDecisions,
  approvalFor,
  counts,
  gatePassed,
  gateRows,
  isOpen,
  loadDecisions,
  postDecision,
  queueOrder,
  saveDecisions,
  type Approval,
  type Decision,
  type QueueFixture,
} from "./producer";

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

  useEffect(() => {
    fetch(`/fixtures/${QUEUE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`queue ${r.status}`))))
      .then((q: QueueFixture) => {
        setFx(q);
        setDecisions(loadDecisions(q.match_id));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const all = useMemo(() => (fx ? applyDecisions(fx.overlays, decisions) : []), [fx, decisions]);
  const queue = useMemo(() => queueOrder(all, openOnly), [all, openOnly]);
  const current = all.find((o) => o.id === selected) ?? queue[0] ?? null;
  const tally = counts(all);

  async function decide(o: Overlay, d: Decision) {
    if (!fx) return;
    const approval = approvalFor(o, d, by, new Date());
    const next = { ...decisions, [o.id]: approval };
    setDecisions(next);
    saveDecisions(fx.match_id, next);
    // Move on to the next open overlay.
    setSelected(queueOrder(applyDecisions(fx.overlays, next), true).find((q) => q.id !== o.id)?.id ?? null);
    if (!secret) return;
    setSent((s) => ({ ...s, [o.id]: "sending…" }));
    const r = await postDecision(fetch, fx.match_id, { ...o, approval }, secret).catch(() => ({ ok: false, status: 0 }));
    setSent((s) => ({ ...s, [o.id]: r.ok ? "sent to hub" : `hub said ${r.status || "unreachable"}` }));
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
      </header>

      <div className="stage">
        <nav className="queue" aria-label="Queue">
          {queue.map((o) => (
            <button key={o.id} className={o.id === current?.id ? "on" : ""} onClick={() => setSelected(o.id)}>
              <b>{minute(o.match_tc)}</b> {o.lens} · {o.side} · {o.lang}
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

function minute(ms: number): string {
  return `${Math.floor(ms / 60_000) + 1}'`;
}
