import { useEffect, useMemo, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { OverlayLayer } from "./components/OverlayLayer";
import { PitchView } from "./components/PitchView";
import { LENSES, SURFACES, type Fixture } from "./fixture/synthetic";
import { applyHubMessage, liveFrame, LiveDirector, liveMatchT, newLiveState } from "./live";
import { frameAt, playStateAt, selectOverlays, timeline, wordIndexAt } from "./playback";
import { useOverlayAudio } from "./useOverlayAudio";
import { connectMatch, matchWsUrl, type SourceMode } from "./ws";

type Surface = Overlay["surface"];
type Lens = Overlay["lens"];

const params = new URLSearchParams(location.search);
/** The hub's match (a `chalktalk_sim` package); the local fixture plays when the hub is down. */
const MATCH_ID = params.get("match") ?? "sim-7";
const FIXTURE_ID = params.get("fixture") ?? "demo-001";

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
  const [error, setError] = useState<string | null>(null);
  const [surface, setSurface] = useState<Surface>("broadcast");
  const [lens, setLens] = useState<Lens>("casual");
  const [mode, setMode] = useState<{ mode: SourceMode; detail?: string }>({ mode: "connecting" });
  const [live, setLive] = useState<Overlay[]>([]);
  const [playing, setPlaying] = useState(true);
  // Hub state lives in a ref: frame batches land every second, renders tick at the frame rate.
  const hub = useRef(newLiveState());
  const director = useRef(new LiveDirector());
  const [hubReady, setHubReady] = useState(false);
  const isLive = mode.mode === "live" && hubReady;
  const { elapsed, seek, seekGen } = usePlayClock(playing || isLive);

  useEffect(() => {
    fetch(`/fixtures/${FIXTURE_ID}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`fixture ${r.status}`))))
      .then(setFixture)
      .catch((e: Error) => setError(e.message));
  }, []);

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
  const overlays = useMemo(() => selectOverlays(source, surface, lens), [source, surface, lens]);
  const tl = useMemo(() => timeline(matchEnd, overlays), [matchEnd, overlays]);
  const loopPos = tl.loopMs ? ((elapsed % tl.loopMs) + tl.loopMs) % tl.loopMs : 0;

  let state, frame;
  if (isLive) {
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
  const audio = useOverlayAudio(state.overlay, state.audioMs, playing || isLive, seekGen);
  const audioMs = audio.audioMs;

  if (error && !isLive) return <main className="app error">Could not load the match fixture: {error}</main>;

  return (
    <main className={`app surface-${surface}`}>
      <header className="bar">
        <h1>ChalkTalk</h1>
        <Segmented label="Surface" value={surface} options={SURFACES} onChange={setSurface} />
        <Segmented label="Lens" value={lens} options={LENSES} onChange={setLens} />
        <span className={`badge ${mode.mode}`} title={mode.detail}>
          {isLive ? (hub.current.ended ? "full time" : "live hub") : mode.mode === "fixture" ? "fixture playback" : "connecting…"}
        </span>
      </header>

      <div className="stage">
        {surface === "show" && !isLive && (
          <nav className="chapters" aria-label="Chapters">
            {tl.starts.map(({ overlay, at }, i) => (
              <button key={overlay.id} className={state.overlay?.id === overlay.id ? "on" : ""} onClick={() => seek(at)}>
                <b>{i + 1}.</b> {overlay.script.text.split(" ").slice(0, 6).join(" ")}…
              </button>
            ))}
          </nav>
        )}
        <div className="screen">
          <PitchView frame={frame}>
            <OverlayLayer overlay={state.overlay} frame={frame} audioMs={audioMs} />
          </PitchView>
          {surface === "broadcast" && <div className="scorebug">HOME 0 – 0 AWAY · {clock(state.matchT)}</div>}
          {state.overlay && <Caption overlay={state.overlay} audioMs={audioMs} />}
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
            max={Math.max(1, Math.round(tl.loopMs))}
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

function Caption({ overlay, audioMs }: { overlay: Overlay; audioMs: number }) {
  const words = overlay.script.words ?? [];
  const at = wordIndexAt(overlay, audioMs);
  return (
    <p className="caption" aria-live="polite">
      {words.map((w, i) => (
        <span key={i} className={i === at ? "now" : i < at ? "said" : ""}>
          {w.text}{" "}
        </span>
      ))}
    </p>
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
