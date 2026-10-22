// Gait for the broadcast figures (spike S3). The clip comes from speed and the facing from the
// gap between heading (travel) and body_heading. The gait phase advances with the ground the
// player actually covers, and each foot is planted at a fixed pitch point for its whole stance,
// so feet never slide whatever the speed or clip changes. Pure, so it unit-tests without WebGL.
import type { Frame } from "@chalktalk/contracts";

export type PlayerState = Frame["players"][number];

export type Clip = "idle" | "walk" | "jog" | "sprint";
export type Facing = "forward" | "back" | "side";
type V2 = [number, number];

/** One full gait cycle (two steps), metres. */
export const STRIDE_M: Record<Clip, number> = { idle: 0.8, walk: 1.4, jog: 2.2, sprint: 3.6 };
/** Swing foot clearance, metres. */
export const LIFT_M: Record<Clip, number> = { idle: 0.03, walk: 0.1, jog: 0.18, sprint: 0.26 };
/** Half the gap between the feet, metres. */
export const FOOT_SPREAD_M = 0.12;
/** Gaps longer than this, or a move further than `TELEPORT_M`, are a seek: start a fresh pose. */
export const RESET_GAP_MS = 500;
export const TELEPORT_M = 5;

export function pickClip(v: number): Clip {
  return v < 0.3 ? "idle" : v < 2.2 ? "walk" : v < 5 ? "jog" : "sprint";
}

/** Smallest angle between two headings, degrees 0..180. */
export function angleGap(a: number, b: number): number {
  return Math.abs(((((a - b) % 360) + 540) % 360) - 180);
}

export function pickFacing(heading: number, bodyHeading: number): Facing {
  const g = angleGap(heading, bodyHeading);
  return g < 60 ? "forward" : g > 120 ? "back" : "side";
}

interface Foot {
  /** Stance: where it is planted. Swing: where it lifted off. */
  at: V2;
  stance: boolean;
}

export interface Gait {
  t: number;
  x: number;
  y: number;
  /** 0..1; foot 0 is in stance for [0, 0.5), foot 1 half a cycle later. */
  phase: number;
  clip: Clip;
  facing: Facing;
  /** Travel and facing, degrees counter-clockwise from +x. */
  heading: number;
  bodyHeading: number;
  feet: [Foot, Foot];
}

const footPhase = (phase: number, i: number) => (phase + i * 0.5) % 1;

/** Where foot `i` lands: half a step ahead of the body along the travel direction. */
function landing(x: number, y: number, heading: number, clip: Clip, i: number): V2 {
  const r = (heading * Math.PI) / 180;
  const ahead = STRIDE_M[clip] / 4;
  const side = i === 0 ? FOOT_SPREAD_M : -FOOT_SPREAD_M;
  return [x + Math.cos(r) * ahead - Math.sin(r) * side, y + Math.sin(r) * ahead + Math.cos(r) * side];
}

function fresh(p: PlayerState, t: number): Gait {
  const clip = pickClip(p.v);
  const bodyHeading = p.body_heading ?? p.heading;
  const g: Gait = { t, x: p.x, y: p.y, phase: 0, clip, facing: pickFacing(p.heading, bodyHeading), heading: p.heading, bodyHeading, feet: [] as unknown as [Foot, Foot] };
  const back = landing(p.x, p.y, p.heading + 180, clip, 1);
  g.feet = [
    { at: landing(p.x, p.y, p.heading, clip, 0), stance: true },
    { at: [back[0], back[1]], stance: false }, // just lifting off behind
  ];
  return g;
}

/** Advance `prev` to the player's state at match time `t`. */
export function stepGait(prev: Gait | undefined, p: PlayerState, t: number): Gait {
  if (!prev) return fresh(p, t);
  const dt = t - prev.t;
  if (dt === 0) return prev; // a held frame keeps its pose
  const d = Math.hypot(p.x - prev.x, p.y - prev.y);
  if (dt < 0 || dt > RESET_GAP_MS || d > TELEPORT_M) return fresh(p, t);

  const clip = pickClip(p.v);
  const bodyHeading = p.body_heading ?? p.heading;
  const phase = prev.phase + d / STRIDE_M[clip];
  const feet = prev.feet.map((f, i): Foot => {
    // Each half cycle is one stance or one swing; nothing changes until the foot crosses into the next.
    if (Math.floor(2 * (prev.phase + i * 0.5)) === Math.floor(2 * (phase + i * 0.5))) return f;
    if (footPhase(phase, i) < 0.5) return { at: landing(p.x, p.y, p.heading, clip, i), stance: true };
    return { at: f.stance ? f.at : landing(p.x, p.y, p.heading + 180, clip, i), stance: false }; // lift off from the plant
  }) as [Foot, Foot];
  return { t, x: p.x, y: p.y, phase: phase % 1, clip, facing: pickFacing(p.heading, bodyHeading), heading: p.heading, bodyHeading, feet };
}

/** Foot `i` in pitch metres, `z` up. A stance foot is exactly its plant. */
export function footPose(g: Gait, i: number): { x: number; y: number; z: number } {
  const f = g.feet[i];
  if (f.stance) return { x: f.at[0], y: f.at[1], z: 0 };
  const s = (footPhase(g.phase, i) - 0.5) / 0.5;
  const [tx, ty] = landing(g.x, g.y, g.heading, g.clip, i);
  return { x: f.at[0] + (tx - f.at[0]) * s, y: f.at[1] + (ty - f.at[1]) * s, z: LIFT_M[g.clip] * Math.sin(Math.PI * s) };
}

/** Arm swing in radians, opposite to the same-side leg. */
export function armSwing(g: Gait, i: number): number {
  const amp = { idle: 0.05, walk: 0.35, jog: 0.6, sprint: 0.9 }[g.clip];
  return amp * Math.sin(2 * Math.PI * (g.phase + i * 0.5)) * (g.facing === "forward" ? 1 : 0.5);
}

/** Pelvis bob (two per cycle) and forward lean, metres and radians. */
export function bodyPose(g: Gait): { bob: number; lean: number } {
  const bob = { idle: 0, walk: 0.02, jog: 0.04, sprint: 0.05 }[g.clip] * (0.5 - 0.5 * Math.cos(4 * Math.PI * g.phase));
  const lean = g.facing === "back" ? -0.1 : { idle: 0, walk: 0.04, jog: 0.12, sprint: 0.25 }[g.clip];
  return { bob, lean };
}
