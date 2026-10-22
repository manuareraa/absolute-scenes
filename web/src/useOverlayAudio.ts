// Plays the active overlay's audio and returns the breakdown time to draw at, read from the
// audio element's clock. Wall time (`fallbackMs`) is used only when there is no audio element
// or the browser blocks playback until the viewer taps "Sound on".
import { useEffect, useRef, useState } from "react";
import type { Overlay } from "@chalktalk/contracts";
import { AudioClock, synthVoiceWav } from "./audio";

export interface OverlayAudio {
  audioMs: number;
  /** Which clock `audioMs` came from. */
  clock: "audio" | "wall";
  blocked: boolean;
  unblock(): void;
}

/** The crew's voice file, else (none, or it failed to load) a synthesized stand-in voice. */
function srcFor(o: Overlay, cache: Map<string, string>, failed: Set<string>): string {
  if (o.script.audio_url && !failed.has(o.id)) return o.script.audio_url;
  let url = cache.get(o.id);
  if (!url) {
    const wav = synthVoiceWav(o.script.words ?? []);
    url = URL.createObjectURL(new Blob([wav.slice().buffer], { type: "audio/wav" }));
    cache.set(o.id, url);
  }
  return url;
}

/**
 * `running` is false while the transport is paused. `seekGen` changes on every user seek, so the
 * audio jumps with the picture.
 */
export function useOverlayAudio(overlay: Overlay | null, fallbackMs: number, running: boolean, seekGen: number): OverlayAudio {
  const el = useRef<HTMLAudioElement | null>(null);
  const clock = useRef(new AudioClock());
  const urls = useRef(new Map<string, string>());
  const failed = useRef(new Set<string>());
  const [failGen, setFailGen] = useState(0);
  const fallback = useRef(fallbackMs);
  fallback.current = fallbackMs;
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    if (typeof Audio === "undefined") return;
    const a = new Audio();
    a.preload = "auto";
    a.dataset.chalktalk = "overlay-audio";
    a.hidden = true;
    // A missing or broken voice file falls back to the stand-in voice instead of going silent.
    a.onerror = () => {
      const id = a.dataset.overlay;
      if (!id || a.src.startsWith("blob:")) return;
      failed.current.add(id);
      delete a.dataset.overlay;
      setFailGen((g) => g + 1);
    };
    document.body.append(a);
    el.current = a;
    const cache = urls.current;
    return () => {
      a.pause();
      a.remove();
      for (const u of cache.values()) URL.revokeObjectURL(u);
      cache.clear();
    };
  }, []);

  const id = overlay?.id ?? null;
  useEffect(() => {
    const a = el.current;
    if (!a) return;
    if (!overlay || !running) {
      a.pause();
      return;
    }
    if (a.dataset.overlay !== overlay.id) {
      a.src = srcFor(overlay, urls.current, failed.current);
      a.dataset.overlay = overlay.id;
    }
    a.currentTime = Math.max(0, fallback.current) / 1000;
    a.play().then(
      () => setBlocked(false),
      () => setBlocked(true),
    );
    // Restart only on a new overlay, a pause flip, a user seek or a failed voice file.
  }, [id, running, seekGen, failGen]);

  const a = el.current;
  if (!overlay || !a || blocked || a.dataset.overlay !== overlay.id) {
    return { audioMs: fallbackMs, clock: "wall", blocked, unblock };
  }
  // Until playback actually starts this holds at the start offset, so strokes wait for the voice.
  return { audioMs: clock.current.read(a.currentTime, !a.paused, performance.now()), clock: "audio", blocked, unblock };

  function unblock() {
    const a = el.current;
    if (!a) return;
    a.currentTime = Math.max(0, fallback.current) / 1000;
    a.play().then(
      () => setBlocked(false),
      () => setBlocked(true),
    );
  }
}
