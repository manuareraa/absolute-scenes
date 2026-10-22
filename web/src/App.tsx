import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { checkLabel, claimWords, slotLabel, evidenceFor, evidenceOverlay, eventsSoFar, frameBetween, replayMatchT, type EvidenceEntry } from "./evidence";
import { PitchView } from "./components/PitchView";
import { LENSES, SIDES, SURFACES, type Fixture } from "./fixture/synthetic";
import { applyHubMessage, liveFrame, LiveDirector, liveMatchT, newLiveState } from "./live";
import { frameAt, playStateAt, selectOverlays, timeline, wordIndexAt } from "./playback";
import { chaptersOf, pickShow, showStateAt, type ShowFixture } from "./show";
import { useOverlayAudio } from "./useOverlayAudio";
import { connectMatch, matchWsUrl, type SourceMode } from "./ws";

type Surface = Overlay["surface"];
type Lens = Overlay["lens"];
type Side = Overlay["side"];
type Claim = Overlay["claims"][number];

const params = new URLSearchParams(location.search);
/** The hub's match (a `chalktalk_sim` package); the local fixture plays when the hub is down. */
const MATCH_ID = params.get("match") ?? "sim-7";
const FIXTURE_ID = params.get("fixture") ?? "demo-001";
/** The post-match show surface plays `postmatch` shows; a crew cache's `audio/` goes in `/fixtures/<id>/`. */
const SHOW_ID = params.get("show") ?? "show-sim-7";
const SHOW_BASE = new URL(`/fixtures/${SHOW_ID}/`, location.href).href;
/** The 2D board is the GPU-light default; `?view=3d` opens the broadcast view, `?quality=high` adds AA and shadows. */
const VIEWS = ["2d", "3d"] as const;
type View = (typeof VIEWS)[number];
const START_VIEW: View = params.get("view") === "3d" ? "3d" : "2d";
const QUALITY = params.get("quality") === "high" ? "high" : "light";
/** Deep links: `?lens=analyst&side=away`. */
const pick = <T extends string>(key: string, options: readonly T[], fallback: T): T => {
  const v = params.get(key);
  return options.includes(v as T) ? (v as T) : fallback;
};
// three.js only loads when the 3D view is first opened.
const Broadcast3D = lazy(() => import("./figures/Broadcast3D"));

/**
 * Wall clock in ms that re-renders on every animation frame while playing, so a stroke shows on
 * the first frame its audio time is reached. `seekGen` counts user seeks.
 */
function usePlayClock(playing: boolean) {
  const [elapsed, setElapsed] = useState(0);
  const [seekGen, setSeekGen] = useState(0);
  const base = useRef({ wall: performance.now(), elapsed: 0 });
  useEffect(() => {
    if (!playing) return;
    base.current = { wall: performance.now(), elapsed };
    let id = 0;
    const tick = () => {
      setElapsed(base.current.elapsed + performance.now() - base.current.wall);
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
    // Restart only when play state flips; `elapsed` is captured as the new base.
  }, [playing]);
  const seek = (ms: number) => {
    base.current = { wall: performance.now(), elapsed: ms };
    setElapsed(ms);
    setSeekGen((g) => g + 1);
  };
  return { elapsed, seek, seekGen };
}

export function App() {
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [showFx, setShowFx] = useState<ShowFixture | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [surface, setSurface] = useState<Surface>("broadcast");
  const [lens, setLens] = useState<Lens>(pick("lens", LENSES, "casual"));
  const [side, setSide] = useState<Side>(pick("side", SIDES, "neutral"));
  const [mode, setMode] = useState<{ mode: SourceMode; detail?: string }>({ mode: "connecting" });
  const [live, setLive] = useState<Overlay[]>([]);
  const [playing, setPlaying] = useState(true);
  const [view, setView] = useState<View>(START_VIEW);
  // Hub state lives in a ref: frame batches land every second, renders tick at the frame rate.
  const hub = useRef(newLiveState());
  const director = useRef(new LiveDirector());
  const [hubReady, setHubReady] = useState(false);
  const isLive = mode.mode === "live" && hubReady;
  const { elapsed, seek, seekGen } = usePlayClock(playing || isLive);
  // Evidence replay: a tapped number pauses the show and loops the window it came from.
  const [replay, setReplay] = useState<{ claim: Claim; entry: EvidenceEntry; resume: boolean } | null>(null);
  const rc = usePlayClock(replay !== null);
  const openEvidence = (claim: Claim) => {
    const entry = evidenceFor(showFx?.evidence, claim);
    if (!entry) return;
    setReplay({ claim, entry, resume: replay?.resume ?? playing });
    setPlaying(false);
    rc.seek(0);
  };
  const closeEvidence = () => {
    if (replay?.resume) setPlaying(true);
    setReplay(null);
  };
  useEffect(() => {
    if (!replay) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeEvidence();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    fetch(`/fixtures/${FIXTURE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`fixture ${r.status}`))))
      .then(setFixture)
      .catch((e: Error) => setError(e.message));
  }, []);

  const wantShow = surface === "show";
  useEffect(() => {
    if (!wantShow || showFx) return;
    // Without a show fixture the show surface keeps playing the demo fixture's show overlays.
    fetch(`/fixtures/${SHOW_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`show ${r.status}`))))
      .then(setShowFx)
      .catch(() => {});
  }, [wantShow, showFx]);

  useEffect(
    () =>
      connectMatch(matchWsUrl(MATCH_ID, location), {
        onMode: (m, detail) => setMode({ mode: m, detail }),
        onMessage: (m) => {
          if (m.type === "overlay") return setLive((prev) => [...prev.filter((p) => p.id !== m.overlay.id), m.overlay]);
          hub.current = applyHubMessage(hub.current, m, performance.now());
          if (m.type === "frames" && m.frames.length) setHubReady(true);
        },
      }),
    [],
  );

  const frames = fixture?.frames ?? [];
  const matchEnd = frames.length ? frames[frames.length - 1].t : 0;
  const source = isLive ? live : (fixture?.overlays ?? []);
  const overlays = useMemo(() => selectOverlays(source, surface, lens, side), [source, surface, lens, side]);
  const tl = useMemo(() => timeline(matchEnd, overlays), [matchEnd, overlays]);
  const show = useMemo(() => (showFx ? pickShow(showFx.shows, lens, side) : undefined), [showFx, lens, side]);
  const book = useMemo(() => (show ? chaptersOf(show, SHOW_BASE) : null), [show]);
  const showMode = wantShow && !isLive && book !== null && showFx !== null;
  const loopMs = showMode ? book.totalMs : tl.loopMs;
  const loopPos = loopMs ? ((elapsed % loopMs) + loopMs) % loopMs : 0;

  let state, frame;
  let chapter = -1;
  if (showMode) {
    state = showStateAt(book.chapters, book.totalMs, elapsed);
    chapter = state.chapter;
    frame = frameAt(showFx.frames, state.matchT);
  } else if (isLive) {
    // Play on the hub's clock; hold on a moment while its breakdown runs, then rejoin live.
    const now = performance.now();
    const liveT = liveMatchT(hub.current, now);
    const cut = director.current.step(overlays, liveT, now);
    const matchT = cut.overlay ? cut.overlay.match_tc : liveT;
    state = { matchT, overlay: cut.overlay, audioMs: cut.audioMs };
    frame = liveFrame(hub.current, matchT);
  } else {
    state = playStateAt(elapsed, matchEnd, overlays);
    frame = frameAt(frames, state.matchT);
  }

  // Strokes and captions run on the overlay audio's clock, not on wall time.
  const audio = useOverlayAudio(state.overlay, state.audioMs, (playing || isLive) && !replay, seekGen);
  const replaying = showMode && replay !== null;
  const replayT = replaying ? replayMatchT(replay.entry, rc.elapsed) : 0;
  if (replaying) frame = frameBetween(showFx.frames, replayT);
  const drawn = replaying ? evidenceOverlay(replay.entry, replay.claim.id) : state.overlay;
  const tappable = (c: Claim) => showMode && evidenceFor(showFx.evidence, c) !== undefined;
  const audioMs = audio.audioMs;
  // Breakdowns cut to the 2D chalkboard, as a broadcast cuts to the telestrator; play stays in 3D.
  const show3d = view === "3d" && !state.overlay;

  if (error && !isLive) return <main className="app error">Could not load the match fixture: {error}</main>;

  return (
    <main className={`app surface-${surface}`}>
      <header className="bar">
        <h1>ChalkTalk</h1>
        <Segmented label="Surface" value={surface} options={SURFACES} onChange={setSurface} />
        <Segmented label="Lens" value={lens} options={LENSES} onChange={setLens} />
        <Segmented label="Side" value={side} options={SIDES} onChange={setSide} />
        <Segmented label="View" value={view} options={VIEWS} onChange={setView} />
        <span className={`badge ${mode.mode}`} title={mode.detail}>
          {isLive ? (hub.current.ended ? "full time" : "live hub") : mode.mode === "fixture" ? "fixture playback" : "connecting…"}
        </span>
      </header>

      <div className="stage">
        {showMode && (
          <nav className="chapters" aria-label="Chapters">
            {book.chapters.map((c, i) => (
              <button key={c.overlay.id} className={chapter === i ? "on" : ""} aria-current={chapter === i} onClick={() => seek(c.at)}>
                <b>{i + 1}.</b> {c.title}
              </button>
            ))}
            {state.overlay && state.overlay.claims.some(tappable) && (
              <div className="claims" aria-label="Numbers in this chapter">
                <h2>Tap a number to see its evidence</h2>
                {state.overlay.claims.filter(tappable).map((c) => (
                  <button key={c.id} className={replay?.claim === c ? "on" : ""} onClick={() => openEvidence(c)}>
                    {slotLabel(c.text_slot)} <b>{String(c.value)}</b> {c.unit ?? ""}
                  </button>
                ))}
              </div>
            )}
          </nav>
        )}
        {surface === "show" && !isLive && !showMode && (
          <nav className="chapters" aria-label="Chapters">
            {tl.starts.map(({ overlay, at }, i) => (
              <button key={overlay.id} className={state.overlay?.id === overlay.id ? "on" : ""} onClick={() => seek(at)}>
                <b>{i + 1}.</b> {overlay.script.text.split(" ").slice(0, 6).join(" ")}…
              </button>
            ))}
          </nav>
        )}
        <div className="screen">
          {view === "3d" && (
            <Suspense fallback={show3d ? <PitchView frame={frame} /> : null}>
              <div className="view3d" hidden={!show3d}>
                <Broadcast3D frame={frame} active={show3d} quality={QUALITY} />
              </div>
            </Suspense>
          )}
          {!show3d && (
            <PitchView frame={frame}>
              <OverlayLayer overlay={drawn} frame={frame} audioMs={replaying ? Infinity : audioMs} />
            </PitchView>
          )}
          {surface === "broadcast" && <div className="scorebug">HOME 0 – 0 AWAY · {clock(state.matchT)}</div>}
          {replaying ? (
            <EvidencePanel claim={replay.claim} entry={replay.entry} t={replayT} onClose={closeEvidence} />
          ) : (
            state.overlay && <Caption overlay={state.overlay} audioMs={audioMs} onClaim={showMode ? openEvidence : undefined} tappable={tappable} />
          )}
          {audio.blocked && state.overlay && (
            <button className="sound-on" onClick={audio.unblock}>
              Sound on
            </button>
          )}
        </div>
      </div>

      {surface !== "broadcast" && !isLive && (
        <footer className="transport">
          <button onClick={() => setPlaying((p) => !p)}>{playing ? "Pause" : "Play"}</button>
          <input
            type="range"
            aria-label="Scrub"
            min={0}
            max={Math.max(1, Math.round(loopMs))}
            value={Math.round(loopPos)}
            onChange={(e) => seek(Number(e.target.value))}
          />
          <span className="tc">{clock(state.matchT)}</span>
        </footer>
      )}
    </main>
  );
}

function clock(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function Caption(props: { overlay: Overlay; audioMs: number; onClaim?: (c: Claim) => void; tappable?: (c: Claim) => boolean }) {
  const { overlay, audioMs, onClaim, tappable } = props;
  const words = overlay.script.words ?? [];
  const at = wordIndexAt(overlay, audioMs);
  const spoken = useMemo(() => claimWords(overlay), [overlay]);
  return (
    <p className="caption" aria-live="polite">
      {words.map((w, i) => {
        const cls = i === at ? "now" : i < at ? "said" : "";
        const c = onClaim ? spoken.get(i) : undefined;
        if (c && tappable?.(c))
          return (
            <span key={i} className={cls}>
              <button className="num" title="Replay the evidence" onClick={() => onClaim!(c)}>
                {w.text}
              </button>{" "}
            </span>
          );
        return (
          <span key={i} className={cls}>
            {w.text}{" "}
          </span>
        );
      })}
    </p>
  );
}

function EvidencePanel({ claim, entry, t, onClose }: { claim: Claim; entry: EvidenceEntry; t: number; onClose(): void }) {
  const seen = eventsSoFar(entry, t);
  return (
    <section className="evidence" aria-label="Evidence">
      <header>
        <b>
          {slotLabel(claim.text_slot)} = {String(claim.value)} {claim.unit ?? ""}
        </b>
        <span className={`check ${entry.check}`}>{checkLabel(entry)}</span>
        <button onClick={onClose}>Back to the show</button>
      </header>
      <p className="call">
        <code>
          {entry.tool}({Object.entries(entry.args).filter(([k]) => k !== "match_id").map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
        </code>{" "}
        · replay {clock(entry.replay.start_t)}–{clock(entry.replay.end_t)} · now {clock(t)}
      </p>
      <ol className="events">
        {seen.slice(-4).map((e) => (
          <li key={`${e.t}-${e.type}`}>
            {clock(e.t)} {e.type.replaceAll("_", " ")} {e.team ?? ""}
          </li>
        ))}
        {!seen.length && <li className="muted">no events yet</li>}
      </ol>
    </section>
  );
}

function Segmented<T extends string>(props: { label: string; value: T; options: readonly T[]; onChange(v: NoInfer<T>): void }) {
  return (
    <div className="seg" role="radiogroup" aria-label={props.label}>
      {props.options.map((o) => (
        <button key={o} role="radio" aria-checked={o === props.value} className={o === props.value ? "on" : ""} onClick={() => props.onChange(o)}>
          {o}
        </button>
      ))}
    </div>
  );
}
