import { describe, expect, it } from "vitest";
import { strokeStartMs } from "@chalktalk/contracts";
import { makeFixture } from "../src/fixture/synthetic";
import { AudioClock, firstOnsetMs, MAX_EXTRAPOLATE_MS, synthVoiceWav } from "../src/audio";

describe("audio clock", () => {
  it("runs smoothly between coarse currentTime steps", () => {
    const c = new AudioClock();
    expect(c.read(1.0, true, 0)).toBe(1000);
    expect(c.read(1.0, true, 10)).toBe(1010);
    expect(c.read(1.02, true, 20)).toBe(1020);
    // currentTime stalls (buffering): the clock stops MAX_EXTRAPOLATE_MS past the last step.
    expect(c.read(1.02, true, 500)).toBe(1020 + MAX_EXTRAPOLATE_MS);
  });

  it("never runs backwards on small noise, but follows a seek", () => {
    const c = new AudioClock();
    c.read(2.0, true, 0);
    expect(c.read(2.0, true, 30)).toBe(2030);
    expect(c.read(2.01, true, 31)).toBe(2030); // step lands behind the extrapolation: hold
    expect(c.read(0.5, true, 40)).toBe(500); // seek back
  });

  it("holds when paused", () => {
    const c = new AudioClock();
    c.read(3.0, true, 0);
    expect(c.read(3.0, false, 1000)).toBe(3000);
  });
});

describe("stand-in voice", () => {
  const o = makeFixture().overlays[0];
  const words = o.script.words ?? [];
  const wav = synthVoiceWav(words);

  it("is a valid 8 kHz 8-bit WAV as long as the script", () => {
    expect(new TextDecoder().decode(wav.slice(0, 4))).toBe("RIFF");
    expect(new DataView(wav.buffer).getUint32(24, true)).toBe(8000);
    const last = words[words.length - 1];
    expect(wav.length - 44).toBe(Math.ceil(((last.offset_ms + last.duration_ms + 200) / 1000) * 8000));
  });

  it("starts each word's sound at its offset, so a cued stroke leads its word by lead_ms", () => {
    for (const w of words) expect(Math.abs(firstOnsetMs(wav, w.offset_ms) - w.offset_ms)).toBeLessThan(2);
    for (const s of o.strokes) {
      const cue = o.script.cues.find((c) => c.cue_id === s.cue_id)!;
      expect(firstOnsetMs(wav, cue.offset_ms) - strokeStartMs(o.script.cues, s)).toBeCloseTo(s.lead_ms ?? 150, -1);
    }
  });
});
