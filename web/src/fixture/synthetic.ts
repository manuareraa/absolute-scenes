// Deterministic synthetic match fixture for the M1 web shell: 25 Hz frames and overlays
// for fictional teams ("home", "away"). No real clubs, players or tracking data.
// Self-contained (type-only imports) so `node scripts/gen-fixture.ts` can run it directly.
import type { Frame, Overlay } from "@chalktalk/contracts";

export const FPS = 25;
export const FRAME_MS = 1000 / FPS;

export interface Fixture {
  match_id: string;
  fps: number;
  frames: Frame[];
  overlays: Overlay[];
}

type P = [number, number];
type Player = Frame["players"][number];
type Stroke = Overlay["strokes"][number];
type Lens = Overlay["lens"];
type Surface = Overlay["surface"];

/** mulberry32: small seeded PRNG so the fixture is identical on every run. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const r2 = (n: number) => Math.round(n * 100) / 100 + 0; // + 0 turns -0 into 0
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

// 4-4-2 anchors for the home side attacking +x; away mirrors them.
const ANCHORS: P[] = [
  [-48, 0],
  [-30, -24], [-33, -8], [-33, 8], [-30, 24],
  [-12, -22], [-15, -6], [-15, 6], [-12, 22],
  [4, -7], [6, 7],
];

// Ball carriers over time (home ids), with the pass arrival times in match ms.
const BALL_CHAIN: { t: number; owner: string }[] = [
  { t: 0, owner: "h7" },
  { t: 2400, owner: "h6" },
  { t: 4000, owner: "h8" },
  { t: 6200, owner: "h10" },
  { t: 9000, owner: "h11" },
  { t: 11000, owner: "h9" },
];

function playerPos(id: string, t: number, ballX: number, phase: number[]): P {
  const team = id[0] === "h" ? 1 : -1;
  const idx = Number(id.slice(1)) - 1;
  const [ax, ay] = ANCHORS[idx];
  // The block shifts with the ball and the attack pushes up over time.
  const push = team === 1 ? (t / 12000) * 14 : (t / 12000) * 8;
  const shift = ballX * 0.35;
  const wobble = Math.sin(t / 900 + phase[idx]) * 1.6;
  const x = team === 1 ? ax + push + shift : -ax * 0.9 + shift + push * 0.5 - 4;
  const y = team * ay * (team === 1 ? 1 : 0.85) + wobble;
  const keeper = idx === 0 ? 0.2 : 1;
  return [clamp(x * keeper + (1 - keeper) * (team === 1 ? -48 : 48), -52, 52), clamp(y, -33, 33)];
}

function ownerAt(t: number): { from: string; to: string; k: number } {
  for (let i = BALL_CHAIN.length - 1; i >= 0; i--) {
    if (t >= BALL_CHAIN[i].t) {
      const next = BALL_CHAIN[i + 1];
      // The pass travels during the last 600 ms before the next carrier receives it.
      if (next && t > next.t - 600) return { from: BALL_CHAIN[i].owner, to: next.owner, k: (t - (next.t - 600)) / 600 };
      return { from: BALL_CHAIN[i].owner, to: BALL_CHAIN[i].owner, k: 0 };
    }
  }
  return { from: "h7", to: "h7", k: 0 };
}

export function makeFrames(seconds = 12, seed = 7): Frame[] {
  const rand = rng(seed);
  const phase = Array.from({ length: 11 }, () => rand() * Math.PI * 2);
  const ids = [
    ...Array.from({ length: 11 }, (_, i) => `h${i + 1}`),
    ...Array.from({ length: 11 }, (_, i) => `a${i + 1}`),
  ];
  const n = Math.round(seconds * FPS);
  const raw: { t: number; pos: Record<string, P>; ball: P; owner: string | null; z: number }[] = [];
  let ballX = 0;
  for (let f = 0; f < n; f++) {
    const t = Math.round(f * FRAME_MS);
    const pos: Record<string, P> = {};
    for (const id of ids) pos[id] = playerPos(id, t, ballX, phase);
    const o = ownerAt(t);
    const a = pos[o.from];
    const b = pos[o.to];
    const ball: P = [a[0] + (b[0] - a[0]) * o.k + 0.6, a[1] + (b[1] - a[1]) * o.k];
    ballX = ball[0];
    pos.ref = [clamp(ball[0] - 8, -50, 50), clamp(ball[1] * 0.5 + 10, -33, 33)];
    raw.push({ t, pos, ball, owner: o.k === 0 ? o.from : null, z: o.k ? Math.sin(Math.PI * o.k) * 0.8 : 0.11 });
  }
  return raw.map((cur, i) => {
    const prev = raw[Math.max(0, i - 1)];
    const dt = i ? (cur.t - prev.t) / 1000 : 1;
    const players: Player[] = [...ids, "ref"].map((id) => {
      const [x, y] = cur.pos[id];
      const [px, py] = prev.pos[id];
      const v = i ? Math.hypot(x - px, y - py) / dt : 0;
      const heading = i && v > 0.05 ? (Math.atan2(y - py, x - px) * 180) / Math.PI : id[0] === "a" ? 180 : 0;
      return { id, team: id === "ref" ? "ref" : id[0] === "h" ? "home" : "away", x: r2(x), y: r2(y), v: r2(v), heading: r2(heading) };
    });
    const bv = i ? Math.hypot(cur.ball[0] - prev.ball[0], cur.ball[1] - prev.ball[1]) / dt : 0;
    return {
      t: cur.t,
      period: 1,
      ball: { x: r2(cur.ball[0]), y: r2(cur.ball[1]), z: r2(cur.z), v: r2(bv), owner: cur.owner },
      players,
    };
  });
}

// --- overlays -------------------------------------------------------------------------

/** Script text with cue markers like "the [k1:gap]" → text, words and cue offsets. */
export function buildScript(marked: string): Overlay["script"] {
  const words: { text: string; offset_ms: number; duration_ms: number }[] = [];
  const cues: { cue_id: string; offset_ms: number }[] = [];
  let at = 300;
  // A marker may span several words ("[k4:offside line]"); its cue lands on the first.
  for (const m of marked.matchAll(/\[(\w+):([^\]]+)\](\S*)|(\S+)/g)) {
    const parts = m[4] ? [m[4]] : (m[2] + m[3]).split(/\s+/);
    if (!m[4]) cues.push({ cue_id: m[1], offset_ms: at });
    for (const text of parts) {
      const duration = Math.max(180, text.length * 55);
      words.push({ text, offset_ms: at, duration_ms: duration });
      at += duration + 70;
    }
  }
  const text = words.map((w) => w.text).join(" ");
  const ssml = `<speak>${marked.replace(/\[(\w+):([^\]]+)\]/g, "<bookmark mark='$1'/>$2")}</speak>`;
  return { ssml, text, cues, words };
}

const LINES: Record<string, Record<Lens, string>> = {
  m1: {
    casual: "Watch this [k1:pass] into the [k2:eight] who has [k3:time] — the [k4:line] is high, [k5:eleven metres] of space.",
    analyst: "Line-breaking [k1:pass] finds the [k2:eight] between lines; [k3:pressure] arrives late, the [k4:offside line] sits at the halfway mark, [k5:11.4 m] gap.",
    newcomer: "Here's the [k1:pass] forward. Our [k2:midfielder] is free with [k3:space] around him. The defenders' [k4:line] is far up, leaving a [k5:big gap].",
  },
  m2: {
    casual: "Now the [k1:run] in behind, the [k2:pocket] opens, it's [k3:on] for the [k4:ten], and if he'd [k5:held] his run, [k6:look] at the space.",
    analyst: "Third-man [k1:run] attacks the [k2:half-space] pocket; [k3:spotlight] on the ten, [k4:carry] then [k5:ghost] path shows the held run, [k6:back line] steps.",
    newcomer: "See the [k1:run] behind? That [k2:area] is empty. The [k3:player] with the ball [k4:moves] it on. A [k5:different] run would [k6:open] even more.",
  },
};

function strokesM1(f: Frame): Stroke[] {
  const by = (id: string) => f.players.find((p) => p.id === id)!;
  const passer = by("h6");
  const recv = by("h8");
  const lastAway = Math.min(...f.players.filter((p) => p.team === "away" && p.id !== "a1").map((p) => p.x));
  return [
    { id: "s1", shape: "pass_lane", geometry_m: { points: [[passer.x, passer.y], [recv.x, recv.y]] }, style: { color: "chalk", width: 1.2 }, cue_id: "k1", lead_ms: 150, duration_ms: 600, claim_ids: ["c1"] },
    { id: "s2", shape: "ring", geometry_m: { player_id: "h8", radius: 2 }, style: { color: "home" }, cue_id: "k2", lead_ms: 150, duration_ms: 400 },
    { id: "s3", shape: "arrow", geometry_m: { points: [[recv.x, recv.y], [recv.x + 8, recv.y + 3]] }, style: { color: "chalk" }, cue_id: "k3", lead_ms: 150, duration_ms: 500 },
    { id: "s4", shape: "offside_line", geometry_m: { points: [[r2(lastAway), 0]] }, style: { color: "danger", dash: true }, cue_id: "k4", lead_ms: 200, duration_ms: 500 },
    { id: "s5", shape: "label", geometry_m: { points: [[r2((recv.x + lastAway) / 2), r2(recv.y + 6)]], text: "11.4 m" }, style: { color: "chalk" }, cue_id: "k5", lead_ms: 150, duration_ms: 400, claim_ids: ["c1"] },
  ];
}

function strokesM2(f: Frame): Stroke[] {
  const by = (id: string) => f.players.find((p) => p.id === id)!;
  const runner = by("h11");
  const ten = by("h10");
  const backs = ["a2", "a3", "a4", "a5"].map(by);
  const backX = r2(Math.min(...backs.map((p) => p.x)));
  return [
    { id: "s1", shape: "run", geometry_m: { points: [[runner.x, runner.y], [runner.x + 6, runner.y + 4], [runner.x + 14, runner.y + 3]] }, style: { color: "home", dash: true }, cue_id: "k1", lead_ms: 150, duration_ms: 700 },
    { id: "s2", shape: "zone", geometry_m: { points: [[ten.x + 3, ten.y - 6], [ten.x + 14, ten.y - 6], [ten.x + 14, ten.y + 6], [ten.x + 3, ten.y + 6]] }, style: { color: "chalk" }, cue_id: "k2", lead_ms: 150, duration_ms: 500, claim_ids: ["c1"] },
    { id: "s3", shape: "spotlight", geometry_m: { player_id: "h10", radius: 3 }, style: { color: "chalk" }, cue_id: "k3", lead_ms: 150, duration_ms: 400 },
    { id: "s4", shape: "arrow", geometry_m: { points: [[ten.x, ten.y], [ten.x + 9, ten.y - 2]] }, style: { color: "chalk" }, cue_id: "k4", lead_ms: 150, duration_ms: 500 },
    { id: "s5", shape: "ghost_path", geometry_m: { points: [[runner.x, runner.y], [runner.x + 4, runner.y - 1], [runner.x + 9, runner.y - 5]] }, style: { color: "ghost", dash: true }, cue_id: "k5", lead_ms: 150, duration_ms: 700 },
    { id: "s6", shape: "line", geometry_m: { points: [[backX, -30], [backX, 30]] }, style: { color: "away", width: 0.4 }, cue_id: "k6", lead_ms: 150, duration_ms: 500 },
  ];
}

const MOMENTS = [
  { key: "m1", t: 4000, strokes: strokesM1, claim: { text_slot: "gap_m", value: 11.4, unit: "m", tool: "line_gap" } },
  { key: "m2", t: 9000, strokes: strokesM2, claim: { text_slot: "pocket_area_m2", value: 132, unit: "m2", tool: "zone_area" } },
] as const;

export const LENSES: Lens[] = ["casual", "analyst", "newcomer"];
export const SURFACES: Surface[] = ["broadcast", "player", "show"];
export const SIDES: Overlay["side"][] = ["home", "away", "neutral"];

export function makeOverlays(frames: Frame[]): Overlay[] {
  const out: Overlay[] = [];
  for (const m of MOMENTS) {
    const frame = frames.find((f) => f.t >= m.t)!;
    const strokes = m.strokes(frame);
    for (const surface of SURFACES) {
      for (const lens of LENSES) {
        out.push({
          id: `${m.key}-${surface}-${lens}`,
          stream_tc: null,
          match_tc: frame.t,
          surface,
          claims: [
            {
              id: "c1",
              text_slot: m.claim.text_slot,
              value: m.claim.value,
              unit: m.claim.unit,
              tool_call: { id: `tc-${m.key}`, name: m.claim.tool, args: { t: frame.t, team: "away" }, output_hash: `sha256:synthetic-${m.key}` },
              evidence_window: { start_t: Math.max(0, frame.t - 2000), end_t: frame.t + 2000 },
              tolerance: 0.5,
              verified: true,
            },
          ],
          strokes,
          script: buildScript(LINES[m.key][lens]),
          camera: { preset: "broadcast", target: [frame.ball.x, frame.ball.y], zoom: 1 },
          lens,
          side: "neutral",
          lang: "en-GB",
          approval: { state: "auto", by: null, at: null },
          gate: { passed: true, scores: { groundedness: 1 } },
        });
      }
    }
  }
  return out;
}

export function makeFixture(): Fixture {
  const frames = makeFrames();
  return { match_id: "demo-001", fps: FPS, frames, overlays: makeOverlays(frames) };
}
