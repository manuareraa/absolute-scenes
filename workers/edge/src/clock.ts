// The match clock as plain data, so it unit-tests in Node and survives hibernation in storage.
// Match time runs from the anchor at `rate` while playing and is frozen while paused.
export interface Clock {
  playing: boolean;
  /** Match ms at the anchor. */
  anchorT: number;
  /** Wall ms (Date.now()) at the anchor. */
  anchorWall: number;
  rate: number;
  durationMs: number;
  /** True once the clock has run at least once (auto-start only on the very first viewer). */
  started: boolean;
}

export function newClock(durationMs: number): Clock {
  return { playing: false, anchorT: 0, anchorWall: 0, rate: 1, durationMs, started: false };
}

export function matchT(c: Clock, now: number): number {
  if (!c.playing) return c.anchorT;
  return clampT(c, c.anchorT + (now - c.anchorWall) * c.rate);
}

function clampT(c: Clock, t: number): number {
  return Math.max(0, Math.min(c.durationMs, Math.round(t)));
}

export function play(c: Clock, now: number): Clock {
  if (c.playing) return c;
  return { ...c, playing: true, started: true, anchorWall: now };
}

export function pause(c: Clock, now: number): Clock {
  if (!c.playing) return c;
  return { ...c, playing: false, anchorT: matchT(c, now), anchorWall: now };
}

export function seek(c: Clock, t: number, now: number): Clock {
  return { ...c, anchorT: clampT(c, t), anchorWall: now };
}

export function setRate(c: Clock, rate: number, now: number): Clock {
  const r = Math.max(0.25, Math.min(8, rate));
  return { ...c, anchorT: matchT(c, now), anchorWall: now, rate: r };
}

export function ended(c: Clock, now: number): boolean {
  return matchT(c, now) >= c.durationMs;
}

export interface ChunkRef {
  file: string;
  start_t: number;
  end_t: number;
  frames: number;
}

/** Indices of the chunks that hold frames with t in [t0, t1). */
export function chunksFor(chunks: ChunkRef[], t0: number, t1: number): number[] {
  const out: number[] = [];
  chunks.forEach((c, i) => {
    if (c.end_t >= t0 && c.start_t < t1) out.push(i);
  });
  return out;
}

export type ClockAction =
  | { action: "play" }
  | { action: "pause" }
  | { action: "seek"; t: number }
  | { action: "rate"; rate: number }
  | { action: "reset" };

export function parseAction(body: unknown): ClockAction | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  switch (b.action) {
    case "play":
    case "pause":
    case "reset":
      return { action: b.action };
    case "seek":
      return typeof b.t === "number" && Number.isFinite(b.t) ? { action: "seek", t: b.t } : null;
    case "rate":
      return typeof b.rate === "number" && Number.isFinite(b.rate) ? { action: "rate", rate: b.rate } : null;
    default:
      return null;
  }
}

export function apply(c: Clock, a: ClockAction, now: number): Clock {
  switch (a.action) {
    case "play":
      return play(c, now);
    case "pause":
      return pause(c, now);
    case "seek":
      return seek(c, a.t, now);
    case "rate":
      return setRate(c, a.rate, now);
    case "reset":
      return newClock(c.durationMs);
  }
}
