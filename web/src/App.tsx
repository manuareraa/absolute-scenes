import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { airStatus, demoOverlays, withDemo } from "./demo";
import { claimWords, slotLabel, evidenceFor, evidenceOverlay, eventsSoFar, geometryOverlay, frameBetween, replayMatchT, type EvidenceEntry } from "./evidence";
import { PitchView } from "./components/PitchView";
import { LENSES, SIDES, SURFACES, type Fixture } from "./fixture/synthetic";
import { chapterTitles, momentHeadline, num, slotWords, tr, type Strings } from "./i18n";
import { applyHubMessage, liveFrame, LiveDirector, liveMatchT, newLiveState } from "./live";
import { frameAt, playStateAt, selectOverlays, timeline, wordIndexAt } from "./playback";
import { chaptersOf, langsOf, pickShow, showStateAt, type ShowFixture } from "./show";
import { decidingMoments, pct, type Moment, type Summary } from "./summary";
import { useOverlayAudio } from "./useOverlayAudio";
import { isProvisional, varBanner, varFor, varGraphics } from "./var";
import { keepConnected, matchWsUrl, type SourceMode } from "./ws";

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
/** The crew's cached, gate-checked overlays for the live match, which the demo airs on its own. */
const QUEUE_ID = params.get("queue") ?? `queue-${MATCH_ID}`;
/** `?demo=off` airs only what a producer approved (the producer's own broadcast link uses it). */
const DEMO = params.get("demo") !== "off";
/** The 2D board is the GPU-light default; `?view=3d` opens the broadcast view, `?quality=high` adds AA and shadows. */
const VIEWS = ["2d", "3d"] as const;
type View = (typeof VIEWS)[number];
// Without WebGL (some locked-down or headless browsers) the 3D view cannot start; offer 2D only.
const WEBGL = (() => {
  try {
    return !!document.createElement("canvas").getContext("webgl2");
  } catch {
    return false;
  }
})();
const VIEW_OPTIONS: readonly View[] = WEBGL ? VIEWS : ["2d"];
const START_VIEW: View = WEBGL && params.get("view") === "3d" ? "3d" : "2d";
const QUALITY = params.get("quality") === "high" ? "high" : "light";
/** Deep links: `?surface=show&lens=analyst&side=away&lang=es-ES`; the URL follows every change. */
const pick = <T extends string>(key: string, options: readonly T[], fallback: T): T => {
  const v = params.get(key);
  return options.includes(v as T) ? (v as T) : fallback;
};
// Player stays reachable by `?surface=player`; the header offers the two a judge needs.
const HEADER_SURFACES: Surface[] = ["show", "broadcast"];
const WELCOME_KEY = "chalktalk.welcome";
const welcomeSeen = () => {
  try {
    return localStorage.getItem(WELCOME_KEY) === "1";
  } catch {
    return false;
  }
};
const rememberWelcome = () => {
  try {
    localStorage.setItem(WELCOME_KEY, "1");
  } catch {
    // Private mode or blocked storage: the card shows again next visit.
  }
};
// three.js only loads when the 3D view is first opened.
const Broadcast3D = lazy(() => import("./figures/Broadcast3D"));
const GOAL_BANNER_MS = 8000;

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

type Goal = { t: number; team: string };

export function App() {
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [showFx, setShowFx] = useState<ShowFixture | null>(null);
  const [showFailed, setShowFailed] = useState(false);
  const [queue, setQueue] = useState<Overlay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [surface, setSurface] = useState<Surface>(pick("surface", SURFACES, "show"));
  const [lens, setLens] = useState<Lens>(pick("lens", LENSES, "casual"));
  const [side, setSide] = useState<Side>(pick("side", SIDES, "neutral"));
  /** Caption and UI language (`?lang=es-ES`). */
  const [lang, setLang] = useState(params.get("lang") ?? "en-GB");
  const [mode, setMode] = useState<{ mode: SourceMode; detail?: string }>({ mode: "connecting" });
  const [live, setLive] = useState<Overlay[]>([]);
  const [playing, setPlaying] = useState(true);
  const [view, setView] = useState<View>(START_VIEW);
  const [welcome, setWelcome] = useState(() => !welcomeSeen() && params.get("welcome") !== "off" && !params.has("demo"));
  const [how, setHow] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const s = tr(lang);
  // Hub state lives in a ref: frame batches land every second, renders tick at the frame rate.
  const hub = useRef(newLiveState());
  const director = useRef(new LiveDirector());
  // Goals seen in the hub's event batches, keyed so a re-sent batch counts once.
  const goals = useRef(new Map<string, Goal>());
  const [hubReady, setHubReady] = useState(false);
  const isLive = mode.mode === "live" && hubReady;
  // The show is a recorded studio programme: it plays its own fixture on its own clock, live hub
  // or not, so its chapters, ghost, VAR, summaries and evidence work on the live Worker too.
  const onShow = surface === "show" && showFx !== null;
  const running = onShow ? playing : playing || isLive;
  const { elapsed, seek, seekGen } = usePlayClock(running);
  // Evidence replay: a tapped number (or summary moment) pauses the show and loops the window it
  // came from. `key` marks what was tapped; `resume` is whether the show was playing.
  const [replay, setReplay] = useState<{ key: string; title: string; entry: EvidenceEntry; resume: boolean } | null>(null);
  // Half-time / catch-up screen, over a paused show; its top moment loops on the board behind it.
  const [summary, setSummary] = useState<{ s: Summary; resume: boolean } | null>(null);
  const rc = usePlayClock(replay !== null || summary !== null);
  const startReplay = (key: string, title: string, entry: EvidenceEntry) => {
    setReplay({ key, title, entry, resume: replay?.resume ?? summary?.resume ?? playing });
    setPlaying(false);
    rc.seek(0);
  };
  const openEvidence = (claim: Claim) => {
    const entry = evidenceFor(showFx?.evidence, claim);
    if (entry) startReplay(claim.id, claimTitle(claim, lang), entry);
  };
  const openMoment = (m: Moment) => startReplay(`m${m.t}`, `${clock(m.t)} · ${momentHeadline(m, lang)}`, m.replay);
  const closeEvidence = () => {
    // Back from a moment goes back to its summary; back from a number resumes the show.
    if (replay?.resume && !summary) setPlaying(true);
    setReplay(null);
    rc.seek(0);
  };
  const openSummary = (sm: Summary) => {
    setReplay(null);
    setSummary({ s: sm, resume: summary?.resume ?? replay?.resume ?? playing });
    setPlaying(false);
    rc.seek(0);
  };
  const closeSummary = () => {
    if (summary?.resume) setPlaying(true);
    setReplay(null);
    setSummary(null);
  };
  const closeWelcome = () => {
    rememberWelcome();
    setWelcome(false);
  };
  const watchShow = () => {
    setSurface("show");
    setLens("analyst");
    setSide("away");
    closeWelcome();
  };
  const watchLive = () => {
    setSurface("broadcast");
    closeWelcome();
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (how) return setHow(false);
      if (welcome) return closeWelcome();
      if (settingsOpen) return setSettingsOpen(false);
      if (replay) closeEvidence();
      else if (summary) closeSummary();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  // The URL follows the picks, so a reload or a shared link opens the same view.
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    for (const [k, v] of [["surface", surface], ["lens", lens], ["side", side], ["lang", lang], ["view", view]]) q.set(k, v);
    history.replaceState(history.state, "", `${location.pathname}?${q}${location.hash}`);
  }, [surface, lens, side, lang, view]);

  useEffect(() => {
    fetch(`/fixtures/${FIXTURE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`fixture ${r.status}`))))
      .then(setFixture)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!DEMO) return;
    fetch(`/fixtures/${QUEUE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`queue ${r.status}`))))
      .then((q: { match_id: string; overlays: Overlay[] }) => q.match_id === MATCH_ID && setQueue(demoOverlays(q)))
      .catch(() => {});
  }, []);

  const wantShow = surface === "show";
  useEffect(() => {
    if (!wantShow || showFx) return;
    // Without a show fixture the show surface keeps playing the demo fixture's show overlays.
    fetch(`/fixtures/${SHOW_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`show ${r.status}`))))
      .then(setShowFx)
      .catch(() => setShowFailed(true));
  }, [wantShow, showFx]);

  useEffect(
    () =>
      keepConnected(matchWsUrl(MATCH_ID, location), {
        onMode: (m, detail) => setMode({ mode: m, detail }),
        onMessage: (m) => {
          if (m.type === "overlay") return setLive((prev) => [...prev.filter((p) => p.id !== m.overlay.id), m.overlay]);
          hub.current = applyHubMessage(hub.current, m, performance.now());
          if (m.type === "frames") {
            for (const e of m.events as { t: number; type: string; team?: string }[]) {
              if (e?.type === "goal" && e.team) goals.current.set(`${e.t}:${e.team}`, { t: e.t, team: e.team });
            }
            if (m.frames.length) setHubReady(true);
          }
        },
      }),
    [],
  );

  const frames = fixture?.frames ?? [];
  const matchEnd = frames.length ? frames[frames.length - 1].t : 0;
  const liveSource = useMemo(() => (DEMO ? withDemo(live, queue) : live), [live, queue]);
  const source = isLive ? liveSource : (fixture?.overlays ?? []);
  const overlays = useMemo(() => selectOverlays(source, surface, lens, side, lang), [source, surface, lens, side, lang]);
  const langs = useMemo(() => langsOf([...source, ...(showFx?.shows ?? [])]), [source, showFx]);
  const tl = useMemo(() => timeline(matchEnd, overlays), [matchEnd, overlays]);
  const show = useMemo(() => (showFx ? pickShow(showFx.shows, lens, side, lang) : undefined), [showFx, lens, side, lang]);
  const book = useMemo(() => (show ? chaptersOf(show, SHOW_BASE) : null), [show]);
  const titles = useMemo(() => (book ? chapterTitles(book.chapters, lang) : []), [book, lang]);
  const showMode = wantShow && book !== null && showFx !== null;
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
  const audio = useOverlayAudio(state.overlay, state.audioMs, running && !replay && !summary, seekGen);
  const replaying = showMode && replay !== null;
  const summing = showMode && summary !== null && !replaying;
  const replayT = replaying ? replayMatchT(replay.entry, rc.elapsed) : 0;
  if (replaying) frame = frameBetween(showFx.frames, replayT);
  const topMoment = summing ? decidingMoments(summary.s)[0] : undefined;
  if (summing) frame = frameBetween(showFx.frames, topMoment ? replayMatchT(topMoment.replay, rc.elapsed) : summary.s.at_t);
  const vm = showMode && !replaying && !summing ? varFor(showFx.var, state.overlay) : undefined;
  const provisional = vm && state.overlay ? isProvisional(vm, state.overlay, audio.audioMs) : false;
  const drawn = replaying
    ? evidenceOverlay(replay.entry, replay.key)
    : summing
      ? geometryOverlay(summary.s.geometry, summary.s.at_t, `summary-${summary.s.kind}`)
      : vm && state.overlay
        ? varGraphics(vm, state.overlay, audio.audioMs)
        : state.overlay;
  const tappable = (c: Claim) => showMode && evidenceFor(showFx.evidence, c) !== undefined;
  const audioMs = audio.audioMs;
  // Breakdowns cut to the 2D chalkboard, as a broadcast cuts to the telestrator; play stays in 3D.
  const show3d = view === "3d" && !state.overlay;

  // Score and goal banner come from goal events, so the sim's goals light them up.
  const matchT = state.matchT;
  const scored = isLive ? [...goals.current.values()].filter((g) => g.t <= matchT) : [];
  const score = { home: scored.filter((g) => g.team === "home").length, away: scored.filter((g) => g.team === "away").length };
  const lastGoal = scored.filter((g) => matchT - g.t < GOAL_BANNER_MS).sort((a, b) => b.t - a.t)[0];
  const ended = isLive && hub.current.ended;
  const status = surface === "broadcast" ? airStatus(overlays, matchT, state.overlay !== null, ended) : null;
  const preRoll = showMode && !replaying && !summing && chapter >= 0 && state.overlay === null;

  if (error && !isLive) return <main className="app error">Could not load the match fixture: {error}</main>;

  const surfaces = surface === "player" ? [...HEADER_SURFACES, "player" as Surface] : HEADER_SURFACES;
  return (
    <main className={`app surface-${surface}`} lang={lang}>
      <header className="bar">
        <h1>ChalkTalk</h1>
        <div id="controls" className={`controls${settingsOpen ? " open" : ""}`}>
          <Segmented s={s} group="surface" value={surface} options={surfaces} onChange={setSurface} />
          <Segmented s={s} group="lens" value={lens} options={LENSES} onChange={setLens} />
          <Segmented s={s} group="side" value={side} options={SIDES} onChange={setSide} />
          {langs.length > 1 && <Segmented s={s} group="lang" value={langs.includes(lang) ? lang : "en-GB"} options={langs} onChange={setLang} />}
          <Segmented s={s} group="view" value={view} options={VIEW_OPTIONS} onChange={setView} />
        </div>
        <span className={`badge ${isLive ? "live" : mode.mode}`} title={isLive ? s.liveHint : mode.mode === "fixture" ? (mode.detail ?? s.recordedHint) : undefined} role="status">
          {isLive ? (ended ? s.fullTime : s.live) : mode.mode === "fixture" ? s.recorded : s.connecting}
        </span>
        <button className="icon" onClick={() => setHow(true)} title={s.howItWorks} aria-label={s.howItWorks}>
          ?
        </button>
        <button
          className="icon settings-toggle"
          onClick={() => setSettingsOpen((o) => !o)}
          title={s.settings}
          aria-label={s.settings}
          aria-expanded={settingsOpen}
          aria-controls="controls"
        >
          ⚙
        </button>
      </header>

      <div className="stage">
        {showMode && (
          <nav className="chapters" aria-label={s.chapters}>
            {book.chapters.map((c, i) => (
              <button key={c.overlay.id} className={chapter === i ? "on" : ""} aria-current={chapter === i} onClick={() => seek(c.at)} title={titles[i]}>
                <b>{i + 1}.</b> {titles[i]}
              </button>
            ))}
            {showFx.summaries && Object.values(showFx.summaries).length > 0 && (
              <div className="claims" aria-label={s.decided}>
                <h2>{s.decided}</h2>
                {Object.values(showFx.summaries).map((sm) => (
                  <button key={sm.kind} className={summary?.s.kind === sm.kind ? "on" : ""} onClick={() => openSummary(sm)}>
                    {summaryName(sm, s)}
                  </button>
                ))}
              </div>
            )}
            {state.overlay && !summary && state.overlay.claims.some(tappable) && (
              <div className="claims" aria-label={s.tapNumber}>
                <h2>{s.tapNumber}</h2>
                {state.overlay.claims.filter(tappable).map((c) => (
                  <button key={c.id} className={replay?.key === c.id ? "on" : ""} onClick={() => openEvidence(c)} title={s.replayEvidence}>
                    {slotWords(slotLabel(c.text_slot), lang)} <b>{num(c.value, lang)}</b> {c.unit ?? ""}
                  </button>
                ))}
              </div>
            )}
          </nav>
        )}
        {surface === "show" && !isLive && !showMode && (
          <nav className="chapters" aria-label={s.chapters}>
            {tl.starts.map(({ overlay, at }, i) => (
              <button key={overlay.id} className={state.overlay?.id === overlay.id ? "on" : ""} onClick={() => seek(at)}>
                <b>{i + 1}.</b> {clock(overlay.match_tc)} · {overlay.script.text.split(" ").slice(0, 6).join(" ")}…
              </button>
            ))}
          </nav>
        )}
        <div className="main-col">
          <div className="screen">
            {view === "3d" && (
              <Suspense fallback={show3d ? <PitchView frame={frame} label={s.pitch} /> : null}>
                <div className="view3d" hidden={!show3d}>
                  <Broadcast3D frame={frame} active={show3d} quality={QUALITY} label={s.broadcast3d} />
                </div>
              </Suspense>
            )}
            {!show3d && (
              <PitchView frame={frame} label={s.pitch}>
                <OverlayLayer overlay={drawn} frame={frame} audioMs={replaying || summing ? Infinity : audioMs} />
              </PitchView>
            )}
            {surface === "broadcast" && (
              <div className="scorebug" role="status" aria-label={`${s.teams.home} ${score.home}, ${s.teams.away} ${score.away}, ${clock(matchT)}`}>
                <span className="team home">{s.teams.home}</span> <b>{score.home} – {score.away}</b> <span className="team away">{s.teams.away}</span>
                <span className="tc">{clock(matchT)}</span>
              </div>
            )}
            {surface === "broadcast" && lastGoal && (
              <div className={`goal-banner ${lastGoal.team}`} role="alert" key={`${lastGoal.t}`}>
                {s.goal}! {s.teams[lastGoal.team] ?? lastGoal.team} · {score.home} – {score.away}
              </div>
            )}
            {status && <StatusPill status={status} s={s} onShow={() => setSurface("show")} />}
            {vm && <VarBanner {...varBanner(vm, provisional, lang)} provisional={provisional} />}
            {wantShow && !showFx && !showFailed && <TitleCard top={s.loading} />}
            {preRoll && <TitleCard key={`ch${chapter}`} top={s.upNext} title={titles[chapter]} />}
            {summing && <TitleCard key={`sum-${summary.s.kind}`} title={summaryName(summary.s, s)} fade />}
            {replaying ? (
              <EvidencePanel title={replay.title} entry={replay.entry} t={replayT} onClose={closeEvidence} back={summary ? s.backToMoments : s.backToShow} s={s} lang={lang} />
            ) : summing ? (
              <SummaryPanel sm={summary.s} onMoment={openMoment} onClose={closeSummary} s={s} lang={lang} />
            ) : (
              state.overlay && <Caption overlay={state.overlay} audioMs={audioMs} onClaim={showMode ? openEvidence : undefined} tappable={tappable} hint={s.replayEvidence} />
            )}
            {audio.blocked && state.overlay && (
              <button className="sound-on" onClick={audio.unblock} aria-label={s.soundOn} title={s.soundOn}>
                {s.soundOn}
              </button>
            )}
          </div>
          <Legend s={s} />
        </div>
      </div>

      {surface !== "broadcast" && (!isLive || showMode) && (
        <footer className="transport">
          <button onClick={() => setPlaying((p) => !p)} aria-label={playing ? s.pause : s.play} title={playing ? s.pause : s.play}>
            {playing ? s.pause : s.play}
          </button>
          <input
            type="range"
            aria-label={s.scrub}
            title={s.scrub}
            min={0}
            max={Math.max(1, Math.round(loopMs))}
            value={Math.round(loopPos)}
            onChange={(e) => seek(Number(e.target.value))}
          />
          <span className="tc">{clock(state.matchT)}</span>
        </footer>
      )}

      {welcome && !how && <Welcome s={s} onShow={watchShow} onLive={watchLive} onHow={() => setHow(true)} onClose={closeWelcome} />}
      {how && <HowItWorks s={s} onClose={() => setHow(false)} />}
    </main>
  );
}

function clock(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

const claimTitle = (c: Claim, lang: string) => `${cap(slotWords(slotLabel(c.text_slot), lang))}: ${num(c.value, lang)}${c.unit ? ` ${c.unit}` : ""}`;
const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1);
const summaryName = (sm: Summary, s: Strings) => (sm.kind === "half_time" ? s.halfTime : s.catchUp(clock(sm.at_t)));

function Welcome({ s, onShow, onLive, onHow, onClose }: { s: Strings; onShow(): void; onLive(): void; onHow(): void; onClose(): void }) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="sheet welcome" role="dialog" aria-modal="true" aria-labelledby="welcome-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="welcome-title">{s.welcomeTitle}</h2>
        <p>{s.tagline}</p>
        <div className="choices">
          <button className="primary" onClick={onShow} autoFocus>
            <b>{s.watchShow}</b>
            <small>{s.watchShowHint}</small>
          </button>
          <button onClick={onLive}>
            <b>{s.watchLive}</b>
            <small>{s.watchLiveHint}</small>
          </button>
          <button onClick={onHow}>
            <b>{s.howItWorks}</b>
          </button>
        </div>
        <button className="close" onClick={onClose} aria-label={s.close} title={s.close}>
          ×
        </button>
      </section>
    </div>
  );
}

function HowItWorks({ s, onClose }: { s: Strings; onClose(): void }) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="sheet how" role="dialog" aria-modal="true" aria-labelledby="how-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="how-title">{s.howItWorks}</h2>
        <ul>
          {s.how.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <button className="close" onClick={onClose} aria-label={s.close} title={s.close} autoFocus>
          ×
        </button>
      </section>
    </div>
  );
}

function StatusPill({ status, s, onShow }: { status: NonNullable<ReturnType<typeof airStatus>>; s: Strings; onShow(): void }) {
  const text =
    status.kind === "on-air" ? s.onAir : status.kind === "next" ? s.nextMoment(clock(status.at)) : status.kind === "full-time" ? s.fullTime : s.noMoreMoments;
  return (
    <div className={`air-pill ${status.kind}`} role="status">
      <span>{text}</span>
      {(status.kind === "none" || status.kind === "full-time") && (
        <button onClick={onShow} title={s.tryShow}>
          {s.tryShow}
        </button>
      )}
    </div>
  );
}

function TitleCard({ top, title, fade }: { top?: string; title?: string; fade?: boolean }) {
  return (
    <div className={`title-card${fade ? " fade" : ""}`} aria-hidden={!title}>
      {top && <small>{top}</small>}
      {title && <b>{title}</b>}
    </div>
  );
}

function Legend({ s }: { s: Strings }) {
  return (
    <ul className="legend" aria-label="Legend">
      <li>
        <i className="dot home" /> {s.teams.home}
      </li>
      <li>
        <i className="dot away" /> {s.teams.away}
      </li>
      <li>
        <i className="dot ref" /> {s.referee}
      </li>
      <li>
        <i className="dot ball" /> {s.ball}
      </li>
    </ul>
  );
}

function Caption(props: { overlay: Overlay; audioMs: number; onClaim?: (c: Claim) => void; tappable?: (c: Claim) => boolean; hint: string }) {
  const { overlay, audioMs, onClaim, tappable, hint } = props;
  const words = overlay.script.words ?? [];
  const at = wordIndexAt(overlay, audioMs);
  const spoken = useMemo(() => claimWords(overlay), [overlay]);
  return (
    <p className="caption" aria-live="polite" lang={overlay.lang}>
      {words.map((w, i) => {
        const cls = i === at ? "now" : i < at ? "said" : "";
        const c = onClaim ? spoken.get(i) : undefined;
        if (c && tappable?.(c))
          return (
            <span key={i} className={cls}>
              <button className="num" title={hint} aria-label={`${w.text}: ${hint}`} onClick={() => onClaim!(c)}>
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

function VarBanner({ title, detail, provisional }: { title: string; detail: string; provisional: boolean }) {
  return (
    <div className={`var-banner ${provisional ? "provisional" : "decided"}`} role="status">
      <b>{title}</b> <span>{detail}</span>
    </div>
  );
}

function SummaryPanel({ sm, onMoment, onClose, s, lang }: { sm: Summary; onMoment(m: Moment): void; onClose(): void; s: Strings; lang: string }) {
  const { home, away } = sm.stats;
  const rows: [string, string, string][] = [
    [s.stats.shots, String(home.shots), String(away.shots)],
    [s.stats.onTarget, String(home.on_target), String(away.on_target)],
    [s.stats.xg, num(home.xg, lang), num(away.xg, lang)],
    [s.stats.possession, pct(home.possession), pct(away.possession)],
    [s.stats.passAccuracy, pct(home.pass_accuracy), pct(away.pass_accuracy)],
  ];
  return (
    <section className="summary" aria-label={summaryName(sm, s)}>
      <header>
        <b>{summaryName(sm, s)}</b>
        <button onClick={onClose}>{s.backToShow}</button>
      </header>
      <p className="score">
        {s.teams.home} <b>{sm.score.home} – {sm.score.away}</b> {s.teams.away}
      </p>
      <table className="stats">
        <tbody>
          {rows.map(([k, h, a]) => (
            <tr key={k}>
              <td>{h}</td>
              <th>{k}</th>
              <td>{a}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ol className="moments">
        {decidingMoments(sm).map((m) => (
          <li key={m.t}>
            <button className={`moment ${m.kind}`} onClick={() => onMoment(m)} title={s.replayMoment}>
              <span className="when">{clock(m.t)}</span>
              <span className="kind">{s.kinds[m.kind] ?? m.kind}</span>
              <span className="headline">{momentHeadline(m, lang)}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="muted">{s.tapMoment}</p>
    </section>
  );
}

function checkSentence(entry: EvidenceEntry, s: Strings, lang: string): string {
  if (entry.check === "match") return entry.hash_match ? s.checks.matchHash : s.checks.match;
  if (entry.check === "differs") return s.checks.differs(num(entry.rerun_value, lang));
  return s.checks.window;
}

function EvidencePanel(props: { title: string; entry: EvidenceEntry; t: number; onClose(): void; back: string; s: Strings; lang: string }) {
  const { title, entry, t, onClose, back, s, lang } = props;
  const seen = eventsSoFar(entry, t);
  return (
    <section className="evidence" aria-label={title}>
      <header>
        <b>{title}</b>
        <button onClick={onClose}>{back}</button>
      </header>
      <p className={`plain ${entry.check}`}>{checkSentence(entry, s, lang)}</p>
      <p className="call">
        {s.replaying(clock(entry.replay.start_t), clock(entry.replay.end_t))} · {clock(t)}
      </p>
      {seen.length > 0 && (
        <ol className="events">
          {seen.slice(-4).map((e) => (
            <li key={`${e.t}-${e.type}`}>
              {clock(e.t)} {s.events[e.type] ?? e.type.replaceAll("_", " ")} {e.team ? (s.teams[e.team] ?? e.team) : ""}
            </li>
          ))}
        </ol>
      )}
      <details className="tool">
        <summary>{s.showToolCall}</summary>
        <code>
          {entry.tool}({Object.entries(entry.args).filter(([k]) => k !== "match_id").map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
        </code>
      </details>
    </section>
  );
}

type Group = keyof Strings["groups"];

function Segmented<T extends string>(props: { s: Strings; group: Group; value: T; options: readonly T[]; onChange(v: NoInfer<T>): void }) {
  const { s, group } = props;
  return (
    <div className="group" title={s.groupHints[group]}>
      <span className="group-label" id={`g-${group}`}>
        {s.groups[group]}
      </span>
      <div className="seg" role="radiogroup" aria-labelledby={`g-${group}`}>
        {props.options.map((o) => (
          <button
            key={o}
            role="radio"
            aria-checked={o === props.value}
            className={o === props.value ? "on" : ""}
            title={s.optionHints[o] ?? s.options[o] ?? o}
            onClick={() => props.onChange(o)}
          >
            {s.options[o] ?? o}
          </button>
        ))}
      </div>
    </div>
  );
}
