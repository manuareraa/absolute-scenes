// A tiny synthetic match package in the format chalktalk_sim writes (manifest, events,
// gzip JSON chunks), built in a temp folder so no binary fixture is committed.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

export const FPS = 25;
export const CHUNK_MS = 2000;

export function writePackage(dir: string, matchId: string, durationMs: number): void {
  const root = join(dir, "matches", matchId);
  mkdirSync(join(root, "chunks"), { recursive: true });
  const chunks = [];
  for (let start = 0, i = 0; start < durationMs; start += CHUNK_MS, i++) {
    const frames = [];
    for (let t = start; t < Math.min(start + CHUNK_MS, durationMs); t += 1000 / FPS) {
      frames.push({
        t,
        period: 1,
        ball: { x: t / 1000, y: 0, z: 0, v: 1, owner: null },
        players: [{ id: "H01", team: "home", x: -40, y: 0, v: 0, heading: 0, body_heading: 0 }],
      });
    }
    const file = `chunks/c${String(i).padStart(5, "0")}.json.gz`;
    writeFileSync(join(root, file), gzipSync(JSON.stringify(frames)));
    chunks.push({ file, start_t: start, end_t: frames[frames.length - 1].t, frames: frames.length });
  }
  const events = [
    { id: "e00001", t: 400, type: "pass", actors: ["H01"], attrs: {}, source: "sim", confidence: 1 },
    { id: "e00002", t: 2600, type: "shot", actors: ["H01"], attrs: {}, source: "sim", confidence: 1 },
  ];
  writeFileSync(join(root, "events.json"), JSON.stringify(events));
  writeFileSync(
    join(root, "manifest.json"),
    JSON.stringify({
      format: 1,
      match_id: matchId,
      seed: 0,
      fps: FPS,
      duration_ms: durationMs,
      chunk_ms: CHUNK_MS,
      chunks,
      events: { file: "events.json", count: events.length },
    }),
  );
  writeFileSync(join(dir, "index.html"), "<!doctype html><title>test</title>");
}

export function overlay(id: string) {
  return {
    id,
    match_tc: 1200,
    surface: "streaming",
    claims: [],
    strokes: [],
    script: { ssml: "<speak/>", text: "", cues: [], words: [] },
    lens: "neutral",
    side: "neutral",
    lang: "en",
    approval: "approved",
  };
}
