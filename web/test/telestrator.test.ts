import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { TELE_BOX, TELE_PX_PER_M, groundMatrix3d, overlayBounds, project } from "../src/figures/telestrator";
import type { Overlay } from "@chalktalk/contracts";

const W = 1280;
const H = 720;

function tvCamera() {
  const cam = new THREE.PerspectiveCamera(24, W / H, 1, 600);
  cam.position.set(8, 27, 74);
  cam.lookAt(12, 0, -5);
  cam.updateMatrixWorld();
  return new THREE.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
}

/** Apply a column-major CSS matrix3d to element pixel (u, v). */
function css(m: number[], u: number, v: number): [number, number] {
  const x = m[0] * u + m[4] * v + m[12];
  const y = m[1] * u + m[5] * v + m[13];
  const w = m[3] * u + m[7] * v + m[15];
  return [x / w, y / w];
}

describe("telestrator homography", () => {
  it("lays every pitch point of the ground SVG where three.js projects it", () => {
    const vp = tvCamera();
    const m = groundMatrix3d(vp.elements, W, H);
    for (const [px, py] of [[0, 0], [30, 20], [-40, -25], [52.5, 34], [-52.5, 10]]) {
      // SVG units are metres with y flipped; the element is TELE_PX_PER_M pixels per metre.
      const u = (px - TELE_BOX.x) * TELE_PX_PER_M;
      const v = (-py - TELE_BOX.y) * TELE_PX_PER_M;
      const p = new THREE.Vector3(px, 0, -py).applyMatrix4(vp);
      const want = [((p.x + 1) * W) / 2, ((1 - p.y) * H) / 2];
      const got = css(m, u, v);
      expect(got[0]).toBeCloseTo(want[0], 3);
      expect(got[1]).toBeCloseTo(want[1], 3);
      expect(project(vp.elements, W, H, [px, 0, -py])![0]).toBeCloseTo(want[0], 3);
    }
  });

  it("keeps w positive in front of the camera", () => {
    const m = groundMatrix3d(tvCamera().elements, W, H);
    expect(m[15]).toBeGreaterThan(0);
  });

  it("returns null for points behind the camera", () => {
    expect(project(tvCamera().elements, W, H, [8, 27, 200])).toBeNull();
  });

  it("frames strokes and players, and only the x of an offside line", () => {
    const overlay = {
      strokes: [
        { id: "a", shape: "arrow", geometry_m: { points: [[10, -5], [30, 8]] } },
        { id: "o", shape: "offside_line", geometry_m: { points: [[36, -34], [36, 34]] } },
        { id: "r", shape: "ring", geometry_m: { player_id: "H09", radius: 2 } },
      ],
    } as unknown as Overlay;
    const box = overlayBounds(overlay, (id) => (id === "H09" ? [20, 12] : undefined));
    expect(box).toEqual({ min: [10, -5], max: [36, 14] });
    expect(overlayBounds(null, () => undefined)).toBeNull();
  });
});
