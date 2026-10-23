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
