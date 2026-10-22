// The audio clock that strokes are scheduled on (overlay.schema: a stroke starts at
// cues[cue_id].offset_ms - lead_ms on the audio clock), and a stand-in voice for overlays
// that carry no `audio_url` yet: one tone burst per word at its offset, so the picture can be
// checked against what is heard before the crew's speech audio exists.
import type { Overlay } from "@chalktalk/contracts";

type Word = NonNullable<Overlay["script"]["words"]>[number];

/** Gap before `currentTime` is trusted to move on its own again (Chrome ticks it every ~10-20 ms). */
export const MAX_EXTRAPOLATE_MS = 60;

/**
 * Smooths `HTMLMediaElement.currentTime`, which only advances in coarse steps. Between steps the
 * clock runs on `performance.now()`, never more than `MAX_EXTRAPOLATE_MS` past the last step and
 * never backwards while playing.
 */
export class AudioClock {
  private lastCt = -1;
  private lastPerf = 0;
  private out = 0;

  read(currentTimeS: number, playing: boolean, perfNow: number): number {
    const ct = currentTimeS * 1000;
    if (ct !== this.lastCt) {
      // A jump back is a seek; small reversals are clock noise and are held.
      if (ct < this.out - 250 || !playing) this.out = ct;
      this.lastCt = ct;
      this.lastPerf = perfNow;
    }
    if (!playing) return (this.out = ct);
    const est = ct + Math.min(MAX_EXTRAPOLATE_MS, perfNow - this.lastPerf);
    return (this.out = Math.max(this.out, est));
  }
}

/** 8-bit mono PCM WAV with a short voiced burst per word (about 8 kB a second). */
export function synthVoiceWav(words: Word[], sampleRate = 8000): Uint8Array {
  const end = words.reduce((m, w) => Math.max(m, w.offset_ms + w.duration_ms), 0) + 200;
  const n = Math.ceil((end / 1000) * sampleRate);
  const buf = new Uint8Array(44 + n);
  const v = new DataView(buf.buffer);
  const tag = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  tag(0, "RIFF");
  v.setUint32(4, 36 + n, true);
  tag(8, "WAVEfmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate, true);
  v.setUint16(32, 1, true);
  v.setUint16(34, 8, true);
  tag(36, "data");
  v.setUint32(40, n, true);
  buf.fill(128, 44);
  words.forEach((w, k) => {
    const f0 = 150 + ((k * 37) % 90);
    const s0 = Math.round((w.offset_ms / 1000) * sampleRate);
    const len = Math.round((Math.max(60, w.duration_ms - 30) / 1000) * sampleRate);
    for (let i = 0; i < len && s0 + i < n; i++) {
      const t = i / sampleRate;
      const env = Math.min(1, i / (0.004 * sampleRate), (len - i) / (0.02 * sampleRate));
      const s = Math.sin(2 * Math.PI * f0 * t) + 0.5 * Math.sin(4 * Math.PI * f0 * t) + 0.25 * Math.sin(6 * Math.PI * f0 * t);
      buf[44 + s0 + i] = Math.round(128 + 70 * env * (s / 1.75));
    }
  });
  return buf;
}

/** Time of the first sample louder than `threshold` (0..127) at or after `fromMs`; for tests. */
export function firstOnsetMs(wav: Uint8Array, fromMs: number, sampleRate = 8000, threshold = 8): number {
  for (let i = Math.round((fromMs / 1000) * sampleRate); 44 + i < wav.length; i++) {
    if (Math.abs(wav[44 + i] - 128) > threshold) return (i / sampleRate) * 1000;
  }
  return -1;
}
