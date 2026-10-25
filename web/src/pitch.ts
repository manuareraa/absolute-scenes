// Pitch geometry in metres. Origin at the centre spot, x along the long axis, y across
// (counter-clockwise, as in the frame contract). SVG y grows downwards, so y is flipped.

export const PITCH_LENGTH = 105;
export const PITCH_WIDTH = 68;
export const HALF_L = PITCH_LENGTH / 2;
export const HALF_W = PITCH_WIDTH / 2;
/** Margin around the touchlines in the SVG view, metres. */
export const MARGIN = 4;
export const VIEW_BOX = `${-HALF_L - MARGIN} ${-HALF_W - MARGIN} ${PITCH_LENGTH + 2 * MARGIN} ${PITCH_WIDTH + 2 * MARGIN}`;

export type Vec = [number, number];

/** Contract point (generated as [unknown, unknown]) to numbers. */
export function toVec(p: readonly unknown[]): Vec {
  return [Number(p[0]), Number(p[1])];
}

/**
 * A player's shirt number from their id. The sim names players by squad number (`H09` is home
 * number 9, `sim/teams.py`) and the M1 fixture by slot (`h7`); the referee has none.
 */
export function shirtNumber(id: string): number | null {
  const m = /^[A-Za-z](\d{1,2})$/.exec(id);
  return m ? Number(m[1]) : null;
}

/** Pitch metres to SVG user units. */
export function toSvg([x, y]: Vec): Vec {
  return [x, -y];
}

export function dist(a: Vec, b: Vec): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

export function polylineLength(pts: Vec[]): number {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += dist(pts[i - 1], pts[i]);
  return total;
}

/** The first `fraction` (0..1) of a polyline by length: the draw-on part of a stroke. */
export function truncatePolyline(pts: Vec[], fraction: number): Vec[] {
  if (pts.length < 2 || fraction >= 1) return pts.slice();
  if (fraction <= 0) return pts.length ? [pts[0]] : [];
  let remaining = polylineLength(pts) * fraction;
  const out: Vec[] = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const seg = dist(pts[i - 1], pts[i]);
    if (seg >= remaining) {
      const k = seg === 0 ? 0 : remaining / seg;
      const [ax, ay] = pts[i - 1];
      out.push([ax + (pts[i][0] - ax) * k, ay + (pts[i][1] - ay) * k]);
      return out;
    }
    remaining -= seg;
    out.push(pts[i]);
  }
  return out;
}

/** SVG path data for a polyline given in pitch metres. */
export function pathD(pts: Vec[]): string {
  return pts
    .map((p, i) => {
      const [x, y] = toSvg(p);
      return `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

/** Arrowhead triangle at the end of a polyline, in SVG units. */
export function arrowHead(pts: Vec[], size = 1.6): string | null {
  if (pts.length < 2) return null;
  const tip = toSvg(pts[pts.length - 1]);
  const prev = toSvg(pts[pts.length - 2]);
  const ang = Math.atan2(tip[1] - prev[1], tip[0] - prev[0]);
  const wing = (a: number): Vec => [tip[0] - size * Math.cos(a), tip[1] - size * Math.sin(a)];
  const l = wing(ang - 0.45);
  const r = wing(ang + 0.45);
  return `M${tip[0].toFixed(2)} ${tip[1].toFixed(2)} L${l[0].toFixed(2)} ${l[1].toFixed(2)} L${r[0].toFixed(2)} ${r[1].toFixed(2)} Z`;
}

/** Discs this far apart (centre to centre, times the disc scale) just touch. */
export const DISC_GAP = 2.6;
/** No disc is drawn more than this far (metres) from where the player is. */
export const MAX_NUDGE = 0.75;
/** The ball is drawn just outside the nearest disc, so it never covers a shirt number. */
export const BALL_CLEAR = 1.9;

/**
 * Where to draw each disc and the ball so no shirt number is hidden. Display only: discs that
 * overlap are nudged apart (never more than `MAX_NUDGE`), and a ball at a player's feet is drawn
 * at the edge of their disc, on the side it is on. Everything else stays where it is.
 */
export function layoutDiscs(players: Vec[], ball: Vec, k = 1): { players: Vec[]; ball: Vec } {
  const gap = DISC_GAP * k;
  const pos = players.map(([x, y]) => [x, y] as Vec);
  for (let pass = 0; pass < 6; pass++) {
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const [dx, dy] = [pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]];
        const d = Math.hypot(dx, dy);
        if (d >= gap) continue;
        // Coincident discs part along x, the same way every frame.
        const [ux, uy] = d > 1e-6 ? [dx / d, dy / d] : [1, 0];
        const push = (gap - d) / 2;
        pos[i] = [pos[i][0] - ux * push, pos[i][1] - uy * push];
        pos[j] = [pos[j][0] + ux * push, pos[j][1] + uy * push];
      }
    }
    for (let i = 0; i < pos.length; i++) {
      const [dx, dy] = [pos[i][0] - players[i][0], pos[i][1] - players[i][1]];
      const d = Math.hypot(dx, dy);
      if (d > MAX_NUDGE) pos[i] = [players[i][0] + (dx / d) * MAX_NUDGE, players[i][1] + (dy / d) * MAX_NUDGE];
    }
  }
  // The nearest spot to the ball clear of every disc, searched outwards in rings.
  const clear = BALL_CLEAR * k;
  const free = (q: Vec) => pos.every((p) => dist(p, q) >= clear - 1e-9);
  let b: Vec = [ball[0], ball[1]];
  search: for (let r = 0.25; !free(b) && r <= 4 * clear; r += 0.25) {
    for (let a = 0; a < 32; a++) {
      const th = (a * Math.PI) / 16;
      const q: Vec = [ball[0] + r * Math.cos(th), ball[1] + r * Math.sin(th)];
      if (free(q)) {
        b = q;
        break search;
      }
    }
  }
  return { players: pos, ball: b };
}
