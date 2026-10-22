import { describe, expect, it } from "vitest";
import { checkSecret } from "../src/auth";
import { apply, chunksFor, ended, matchT, newClock, parseAction, pause, play, seek, setRate } from "../src/clock";
import { checkOverlay } from "../src/overlay";
import { overlay } from "./fixture";

describe("clock", () => {
  it("runs from the anchor while playing and freezes on pause", () => {
    let c = newClock(10_000);
    expect(matchT(c, 1_000)).toBe(0);
    c = play(c, 1_000);
    expect(matchT(c, 3_500)).toBe(2_500);
    c = pause(c, 3_500);
    expect(matchT(c, 99_000)).toBe(2_500);
    expect(play(c, 5_000).anchorT).toBe(2_500);
  });
  it("clamps to the match and reports the end", () => {
    const c = play(newClock(10_000), 0);
    expect(matchT(c, 50_000)).toBe(10_000);
    expect(ended(c, 50_000)).toBe(true);
    expect(matchT(seek(c, -5, 0), 0)).toBe(0);
  });
  it("changes rate without a jump", () => {
    let c = play(newClock(100_000), 0);
    c = setRate(c, 2, 1_000);
    expect(matchT(c, 1_000)).toBe(1_000);
    expect(matchT(c, 2_000)).toBe(3_000);
    expect(setRate(c, 100, 0).rate).toBe(8);
  });
  it("parses and applies control actions", () => {
    expect(parseAction({ action: "seek", t: 5 })).toEqual({ action: "seek", t: 5 });
    expect(parseAction({ action: "seek" })).toBeNull();
    expect(parseAction({ action: "nope" })).toBeNull();
    expect(parseAction(null)).toBeNull();
    const c = apply(play(newClock(1_000), 0), { action: "reset" }, 10);
    expect(c.playing).toBe(false);
    expect(c.started).toBe(false);
  });
  it("finds the chunks for a window", () => {
    const chunks = [0, 1, 2].map((i) => ({ file: `c${i}`, start_t: i * 10_000, end_t: i * 10_000 + 9_960, frames: 250 }));
    expect(chunksFor(chunks, 0, 1_000)).toEqual([0]);
    expect(chunksFor(chunks, 9_500, 10_500)).toEqual([0, 1]);
    expect(chunksFor(chunks, 9_970, 10_000)).toEqual([]);
    expect(chunksFor(chunks, 29_000, 31_000)).toEqual([2]);
  });
});

describe("secret", () => {
  const req = (h?: string) => new Request("https://x/", { headers: h ? { "x-chalktalk-secret": h } : {} });
  it("accepts only the exact secret", async () => {
    expect(await checkSecret(req("s3cret"), "s3cret")).toBe(true);
    expect(await checkSecret(req("s3cre"), "s3cret")).toBe(false);
    expect(await checkSecret(req(), "s3cret")).toBe(false);
    expect(await checkSecret(req("s3cret"), undefined)).toBe(false);
    expect(await checkSecret(req(""), "")).toBe(false);
  });
});

describe("overlay shape", () => {
  it("accepts a contract overlay and rejects junk", () => {
    expect(checkOverlay({ match_id: "m", overlay: overlay("a") })).toBeNull();
    expect(checkOverlay({ overlay: overlay("a") })).toMatch(/match_id/);
    expect(checkOverlay({ match_id: "m", overlay: { ...overlay("a"), strokes: 1 } })).toMatch(/strokes/);
    expect(checkOverlay("x")).not.toBeNull();
  });
});
