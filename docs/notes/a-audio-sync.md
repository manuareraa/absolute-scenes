# Stream A: strokes on the audio clock, and the draw-sync measurement

## What the player does
- The active overlay's audio plays through one `<audio data-chalktalk>` element.
- The source is `script.audio_url`. Until the crew ships audio, a stand-in voice is synthesized in the browser (`web/src/audio.ts`): an 8 kHz, 8-bit WAV with a tone burst at each word's `offset_ms`, about 8 kB a second, so nothing is added to the bundle or the repo.
- Strokes and captions are timed from the element's `currentTime`, smoothed by `AudioClock`:
  - it extrapolates on `performance.now()` between the coarse steps, at most 60 ms;
  - it never runs backwards except on a seek.
- A stroke starts at `cue.offset_ms - lead_ms`, per the contract.
- The picture re-renders on `requestAnimationFrame`; it used to tick every 40 ms on `setInterval`.
- The breakdown hold is still measured on wall time. The audio's start latency eats into the 900 ms tail.
- If the browser blocks autoplay, the player falls back to wall time and shows a "Sound on" button. Tapping it resumes the audio at the current position.

## Measurement (BUILD-PLAN §8)
`npm run build -w web && npm run test:e2e -w web` runs `web/e2e/sync.e2e.ts` in headless Chromium against `vite preview`, without a hub, on fixture playback.
- For each of the 6 breakdowns (3 lenses × 2 moments), the test clicks the chapter, which restarts the breakdown.
- A MutationObserver records when each stroke is inserted into the DOM.
- Page time is mapped onto the audio clock using the steps of the element's `currentTime`.
- The error is that audio time minus the stroke's scheduled start. Positive means late.

Result on this machine (Chromium 1223 headless, 2026-10-22):

| strokes | median abs | p95 abs | max | signed median |
|---|---|---|---|---|
| 33 | 10 ms | 16 ms | 16 ms | +10 ms (late) |

The errors all fall within one 60 Hz frame. They come from waiting for the next animation frame. The test fails if the median exceeds 40 ms or the p95 exceeds 80 ms.

**Not covered:**
- Audio output latency after `currentTime`, such as Bluetooth or OS mixer buffering, which `HTMLMediaElement` cannot report.
- The paint after DOM insertion, at most one more frame.

## Request for D (CI)
- Playwright is not in CI yet. A job would need `npx playwright install --with-deps chromium`, then `npm run build -w web`, then `npm run test:e2e -w web`.
- The job takes about 45 s. It writes `web/test-results/draw-sync.json`, which is worth keeping as an artifact.
