// Runs one "Ask the pundit" session at a time: streams the crew's events into the control-room
// state, then plays the answer overlay on its own clock. A new question (typed or spoken) barges
// in: the running stream is aborted and the answer on screen stops.
import { useEffect, useRef, useState } from "react";
import { answerEndMs, AskUnavailable, fakeAsk, idleStudio, liveAsk, startStudio, studioReduce, type AskEvent, type AskRequest, type AskSource, type StudioState } from "../ask";

export interface AskHooks {
  /** Pause the show; returns whether it was playing, so closing can resume it. */
  pause(): boolean;
  resume(): void;
}

export interface Studio {
  state: StudioState;
  open: boolean;
  /** Breakdown time of the answer overlay, on the wall clock (the audio clock overrides it). */
  answerMs: number;
  /** True while the answer is still speaking. */
  playing: boolean;
  /** Changes on every new answer, so its audio restarts even with the same overlay id. */
  gen: number;
  /** Pause the show for the bar; closing the studio resumes it if it was playing. */
  pauseShow(): void;
  ask(req: AskRequest): void;
  /** Barge-in: stop the stream and the answer, keep the strip open. */
  stop(): void;
  close(): void;
}

type Runner = (req: AskRequest, signal: AbortSignal) => AsyncGenerator<AskEvent>;

export function useAsk(mode: "live" | "rehearsal" | "auto", hooks: AskHooks, hold: boolean, runners: { live?: Runner; fake?: Runner } = {}): Studio {
  const [state, setState] = useState<StudioState>(idleStudio);
  const [gen, setGen] = useState(0);
  const ctl = useRef<AbortController | null>(null);
  const resume = useRef<boolean | null>(null);
  // Once the route answers 404, later questions go straight to the rehearsal feed.
  const noBackend = useRef(mode === "rehearsal");
  const live = runners.live ?? liveAsk;
  const fake = runners.fake ?? ((req: AskRequest, signal: AbortSignal) => fakeAsk(req, signal));

  const halt = () => {
    ctl.current?.abort();
    ctl.current = null;
  };

  const pauseShow = () => {
    if (resume.current === null) resume.current = hooks.pause();
  };

  const ask = (req: AskRequest) => {
    halt();
    pauseShow();
    const c = new AbortController();
    ctl.current = c;
    const source: AskSource = noBackend.current ? "rehearsal" : "live";
    setState(startStudio(req.question, source));
    setGen((g) => g + 1);
    const feed = (ev: AskEvent) => {
      if (!c.signal.aborted) setState((s) => studioReduce(s, ev));
    };
    void (async () => {
      try {
        if (source === "live") {
          try {
            for await (const ev of live(req, c.signal)) feed(ev);
            return;
          } catch (e) {
            if (!(e instanceof AskUnavailable) || mode === "live") throw e;
            noBackend.current = true;
            if (c.signal.aborted) return;
            setState((s) => ({ ...s, source: "rehearsal" }));
          }
        }
        for await (const ev of fake(req, c.signal)) feed(ev);
      } catch (e) {
        if (c.signal.aborted) return;
        feed({ type: "error", seq: 0, t_ms: 0, text: e instanceof AskUnavailable ? "off" : "" });
      }
    })();
  };

  const stop = () => {
    halt();
    setState((s) => (s.phase === "idle" ? s : { ...s, phase: "done", active: null, overlay: null }));
  };

  const close = () => {
    halt();
    setState(idleStudio);
    if (resume.current) hooks.resume();
    resume.current = null;
  };

  useEffect(() => () => halt(), []);

  // The answer's own clock: starts when its overlay arrives, holds while evidence is open.
  const overlay = state.overlay;
  const endMs = overlay ? answerEndMs(overlay) : 0;
  const [answerMs, setAnswerMs] = useState(0);
  const base = useRef({ wall: 0, ms: 0 });
  useEffect(() => {
    base.current = { wall: performance.now(), ms: 0 };
    setAnswerMs(0);
  }, [overlay, gen]);
  const playing = overlay !== null && answerMs < endMs;
  useEffect(() => {
    if (!overlay || hold || !playing) return;
    base.current = { wall: performance.now(), ms: base.current.ms };
    let id = 0;
    const tick = () => {
      const ms = Math.min(endMs, base.current.ms + performance.now() - base.current.wall);
      setAnswerMs(ms);
      if (ms < endMs) id = requestAnimationFrame(tick);
      else base.current.ms = ms;
    };
    id = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(id);
      base.current.ms = Math.min(endMs, base.current.ms + performance.now() - base.current.wall);
    };
  }, [overlay, gen, hold, playing]);

  return { state, open: state.phase !== "idle", answerMs, playing: playing && !hold, gen, pauseShow, ask, stop, close };
}
