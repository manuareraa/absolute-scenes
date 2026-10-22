// Draw-sync measurement (BUILD-PLAN §8): for every stroke, when it appears on screen versus
// when the audio clock reaches its scheduled start (cue offset - lead_ms). The stand-in voice
// sounds each word exactly at its offset, so this is the error a viewer would hear.
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import type { Overlay } from "@chalktalk/contracts";

const fixture = JSON.parse(readFileSync(new URL("../public/fixtures/demo-001.json", import.meta.url), "utf8")) as { overlays: Overlay[] };
const byId = new Map(fixture.overlays.map((o) => [o.id, o]));

// The contract's timing rule (contracts `strokeStartMs`; that module's JSON imports do not load
// under Playwright's Node loader).
function strokeStartMs(cues: Overlay["script"]["cues"], s: Overlay["strokes"][number]): number {
  const cue = cues.find((c) => c.cue_id === s.cue_id)!;
  return Math.max(0, cue.offset_ms - (s.lead_ms ?? 150));
}

interface Probe {
  epoch: number;
  shown: { epoch: number; overlay: string; stroke: string; perf: number }[];
  audio: { overlay: string; perf: number; ct: number }[];
  /** Start a new measurement; strokes already on screen are not counted. */
  reset(): void;
}

test("strokes land on the audio clock", async ({ page }) => {
  await page.addInitScript(() => {
    const seen = new Set<string>();
    const probe: Probe = {
      epoch: 0,
      shown: [],
      audio: [],
      reset() {
        probe.epoch++;
        seen.clear();
        for (const el of document.querySelectorAll<SVGElement>("[data-overlay] [data-stroke]")) {
          seen.add(`${el.closest<SVGElement>("[data-overlay]")!.dataset.overlay}/${el.dataset.stroke}`);
        }
      },
    };
    (window as unknown as { __probe: Probe }).__probe = probe;
    // DOM insertion time of each stroke; it is painted on the next frame.
    new MutationObserver(() => {
      const perf = performance.now();
      for (const el of document.querySelectorAll<SVGElement>("[data-overlay] [data-stroke]")) {
        const overlay = el.closest<SVGElement>("[data-overlay]")!.dataset.overlay!;
        const key = `${overlay}/${el.dataset.stroke}`;
        if (!seen.has(key)) {
          seen.add(key);
          probe.shown.push({ epoch: probe.epoch, overlay, stroke: el.dataset.stroke!, perf });
        }
      }
    }).observe(document, { subtree: true, childList: true });
    // Steps of the audio element's clock, to map page time onto audio time.
    let last = -1;
    const sample = () => {
      const a = document.querySelector<HTMLAudioElement>("audio[data-chalktalk]");
      if (a && !a.paused && a.currentTime !== last) {
        last = a.currentTime;
        probe.audio.push({ overlay: a.dataset.overlay ?? "", perf: performance.now(), ct: a.currentTime * 1000 });
      }
      setTimeout(sample, 2);
    };
    sample();
  });

  await page.goto("/?match=e2e-no-hub");
  await expect(page.locator(".badge")).toHaveText("fixture playback", { timeout: 10_000 });
  await page.getByRole("radio", { name: "show" }).click();

  // One measurement per chapter click: the breakdown restarts from its first word.
  const visited: { epoch: number; overlay: string }[] = [];
  for (const lens of ["casual", "analyst", "newcomer"]) {
    await page.getByRole("radio", { name: lens }).click();
    const chapters = page.locator(".chapters button");
    for (let i = 0; i < (await chapters.count()); i++) {
      const epoch = await page.evaluate(() => {
        const p = (window as unknown as { __probe: Probe }).__probe;
        p.reset();
        return p.epoch;
      });
      await chapters.nth(i).click();
      const id = await page.locator("g[data-overlay]").getAttribute("data-overlay", { timeout: 5000 });
      const o = byId.get(id!)!;
      visited.push({ epoch, overlay: o.id });
      await expect(page.locator("g[data-overlay] [data-stroke]")).toHaveCount(o.strokes.length, { timeout: 15_000 });
      await page.waitForTimeout(300);
    }
  }

  const probe = await page.evaluate(() => (window as unknown as { __probe: Probe }).__probe);
  const errors: { overlay: string; stroke: string; ms: number }[] = [];
  for (const s of probe.shown) {
    if (!visited.some((v) => v.epoch === s.epoch && v.overlay === s.overlay)) continue;
    const o = byId.get(s.overlay)!;
    const stroke = o.strokes.find((k) => k.id === s.stroke)!;
    // Audio time at page time `perf`: offset between the two clocks over this overlay's steps,
    // taken from the steps nearest the stroke (the clock ticks in ~10 ms steps).
    const steps = probe.audio.filter((a) => a.overlay === s.overlay).sort((a, b) => Math.abs(a.perf - s.perf) - Math.abs(b.perf - s.perf)).slice(0, 7);
    if (!steps.length) continue;
    const offs = steps.map((a) => a.ct - a.perf).sort((a, b) => a - b);
    const audioAt = s.perf + offs[offs.length >> 1];
    errors.push({ overlay: s.overlay, stroke: s.stroke, ms: Math.round(audioAt - strokeStartMs(o.script.cues, stroke)) });
  }

  const abs = errors.map((e) => Math.abs(e.ms)).sort((a, b) => a - b);
  const q = (p: number) => abs[Math.min(abs.length - 1, Math.floor(p * abs.length))];
  const signed = errors.map((e) => e.ms).sort((a, b) => a - b);
  const report = {
    strokes: errors.length,
    overlays: visited.length,
    median_abs_ms: q(0.5),
    p95_abs_ms: q(0.95),
    max_abs_ms: abs[abs.length - 1],
    median_signed_ms: signed[signed.length >> 1],
    errors,
  };
  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/draw-sync.json", JSON.stringify(report, null, 2));
  console.log(`draw sync over ${report.strokes} strokes: median ${report.median_abs_ms} ms, p95 ${report.p95_abs_ms} ms, max ${report.max_abs_ms} ms (signed median ${report.median_signed_ms} ms, + = late)`);

  expect(errors.length).toBeGreaterThanOrEqual(10);
  expect(report.median_abs_ms).toBeLessThanOrEqual(40);
  expect(report.p95_abs_ms).toBeLessThanOrEqual(80);
});
