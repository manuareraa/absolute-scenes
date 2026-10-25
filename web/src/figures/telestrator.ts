// The telestrator on the 3D view: the board's SVG overlay, unchanged, laid on the grass. A camera
// maps the ground plane to the screen by a homography, and a CSS `matrix3d` can express any
// homography, so the SVG is drawn in pitch metres and transformed per frame. Stroke timing stays in
// `OverlayLayer`/`strokeProgress`. Pure, so it unit-tests without WebGL.
import type { Overlay } from "@chalktalk/contracts";
import { HALF_L, HALF_W, MARGIN, toVec, type Vec } from "../pitch";

/** CSS pixels per metre of the ground SVG before projection (sharp enough for a close camera). */
export const TELE_PX_PER_M = 20;
/** The ground SVG's box in SVG units (metres, y flipped): the board's view box. */
export const TELE_BOX = { x: -HALF_L - MARGIN, y: -HALF_W - MARGIN, w: 2 * (HALF_L + MARGIN), h: 2 * (HALF_W + MARGIN) };

/**
 * The CSS `matrix3d` (16 numbers, column-major) that lays an element of TELE_BOX * TELE_PX_PER_M
 * CSS pixels (transform-origin 0 0) on the ground plane y = 0, as seen through `viewProj`
 * (projection x inverse view, column-major as in three.js `Matrix4.elements`) in a `width` x
 * `height` canvas. World axes as in the 3D view: pitch (x, y) is world (x, 0, -y), which is SVG
 * (x, y_svg) = world (x, 0, y_svg).
 */
export function groundMatrix3d(viewProj: ArrayLike<number>, width: number, height: number): number[] {
  const m = (r: number, c: number) => viewProj[c * 4 + r];
  const k = 1 / TELE_PX_PER_M;
  // Element pixel (u, v) -> world (x0 + u k, 0, z0 + v k, 1); the clip row r is a u + b v + c.
  const row = (r: number): Vec3 => [m(r, 0) * k, m(r, 2) * k, m(r, 0) * TELE_BOX.x + m(r, 2) * TELE_BOX.y + m(r, 3)];
  const [cx, cy, cw] = [row(0), row(1), row(3)];
  // Screen pixels: sx = (cx / cw + 1) W / 2, sy = (1 - cy / cw) H / 2, in homogeneous form.
  const hx = cx.map((v, i) => ((v + cw[i]) * width) / 2) as Vec3;
  const hy = cy.map((v, i) => ((cw[i] - v) * height) / 2) as Vec3;
  // Scale for numeric range only; keep the sign so w stays positive in front of the camera.
  const s = cw[2] === 0 ? 1 : 1 / Math.abs(cw[2]);
  const [a, b, w] = [hx, hy, cw].map((r) => r.map((v) => v * s) as Vec3);
  return [a[0], b[0], 0, w[0], a[1], b[1], 0, w[1], 0, 0, 1, 0, a[2], b[2], 0, w[2]];
}
type Vec3 = [number, number, number];

/** Screen pixel of world point (x, y, z), or null behind the camera. */
export function project(viewProj: ArrayLike<number>, width: number, height: number, p: Vec3): Vec | null {
  const m = (r: number, c: number) => viewProj[c * 4 + r];
  const clip = (r: number) => m(r, 0) * p[0] + m(r, 1) * p[1] + m(r, 2) * p[2] + m(r, 3);
  const w = clip(3);
  if (w <= 1e-6) return null;
  return [((clip(0) / w + 1) * width) / 2, ((1 - clip(1) / w) * height) / 2];
}

/** Pitch-metre box of everything an overlay draws, for the camera to frame; null when empty. */
export function overlayBounds(overlay: Overlay | null, playerAt: (id: string) => Vec | undefined): { min: Vec; max: Vec } | null {
  if (!overlay) return null;
  const pts: Vec[] = [];
  for (const s of overlay.strokes) {
    const g = s.geometry_m;
    if (s.shape === "offside_line") {
      // A full-width line: frame its x, not both touchlines.
      if (g.points?.length) pts.push([toVec(g.points[0])[0], 0]);
      continue;
    }
    for (const p of g.points ?? []) pts.push(toVec(p));
    const at = g.player_id ? playerAt(g.player_id) : undefined;
    if (at) {
      const r = g.radius ?? 0;
      pts.push([at[0] - r, at[1] - r], [at[0] + r, at[1] + r]);
    }
  }
  if (!pts.length) return null;
  const min: Vec = [Infinity, Infinity];
  const max: Vec = [-Infinity, -Infinity];
  for (const [x, y] of pts) {
    min[0] = Math.min(min[0], x);
    min[1] = Math.min(min[1], y);
    max[0] = Math.max(max[0], x);
    max[1] = Math.max(max[1], y);
  }
  return { min, max };
}
