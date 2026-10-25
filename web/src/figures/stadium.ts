// Procedural textures for the broadcast view, drawn once on canvases: no image files, no real
// marks. The boards carry only our own name.
import * as THREE from "three";
import { HALF_L, HALF_W } from "../pitch";

/** Grass plane size, metres: the pitch plus its run-off. */
export const GRASS_L = 2 * HALF_L + 16;
export const GRASS_W = 2 * HALF_W + 14;

/** A small seeded PRNG, so the textures are the same on every load. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!];
}

function texture(c: HTMLCanvasElement, maxAniso = 1): THREE.CanvasTexture {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = maxAniso;
  return t;
}

/**
 * The grass: mowing stripes across the pitch (12 bands, as on match day), a fine blade grain and
 * the floodlights' soft fall-off towards the corners.
 */
export function grassTexture(maxAniso: number): THREE.CanvasTexture {
  const ppm = 16;
  const [c, g] = canvas(Math.round(GRASS_L * ppm), Math.round(GRASS_W * ppm));
  const px = (m: number) => m * ppm;
  const x0 = px(GRASS_L / 2 - HALF_L);
  const y0 = px(GRASS_W / 2 - HALF_W);
  g.fillStyle = "#2c6a37";
  g.fillRect(0, 0, c.width, c.height);
  const bands = 12;
  const bw = px((2 * HALF_L) / bands);
  // Stripes run past the touchlines into the run-off, as a mower does.
  for (let i = 0; i < bands; i++) {
    g.fillStyle = i % 2 ? "#2f733b" : "#286232";
    g.fillRect(x0 + i * bw, y0 - px(3), bw, px(2 * HALF_W + 6));
  }
  // Grain: short, faint blades in both shades.
  const r = rng(7);
  for (let i = 0; i < 90000; i++) {
    g.fillStyle = r() < 0.5 ? "rgba(255,255,230,0.035)" : "rgba(0,20,0,0.05)";
    g.fillRect(r() * c.width, r() * c.height, 1 + r() * 2, 1);
  }
  // Floodlight fall-off: brighter in the middle, darker into the corners.
  const lg = g.createRadialGradient(c.width / 2, c.height / 2, c.height * 0.15, c.width / 2, c.height / 2, c.width * 0.62);
  lg.addColorStop(0, "rgba(255,255,220,0.10)");
  lg.addColorStop(1, "rgba(0,8,0,0.38)");
  g.fillStyle = lg;
  g.fillRect(0, 0, c.width, c.height);
  const t = texture(c, maxAniso);
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  return t;
}

/**
 * A crowd in the stands: muted, mostly dark seats with scattered colour, no banners or marks.
 * Anisotropic, so the end stands do not shimmer into streaks at a grazing angle.
 */
export function crowdTexture(maxAniso = 1): THREE.CanvasTexture {
  const [c, g] = canvas(1024, 256);
  g.fillStyle = "#14181c";
  g.fillRect(0, 0, c.width, c.height);
  const r = rng(11);
  const tones = ["#23272d", "#2e3238", "#3b3e43", "#4a4844", "#1f2a3c", "#3b2426", "#5e5c56", "#7a756b"];
  for (let row = 0; row < 32; row++) {
    // Each row a step: a thin darker lip under it.
    g.fillStyle = "#0c0e10";
    g.fillRect(0, row * 8 + 7, c.width, 1);
    for (let x = 0; x < c.width; x += 4) {
      if (r() < 0.12) continue;
      g.fillStyle = tones[Math.floor(r() * tones.length)];
      g.fillRect(x + r(), row * 8 + 2 + r() * 2, 3, 4);
    }
  }
  const t = texture(c, maxAniso);
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

/** Pitch-side boards: dark with our own name in chalk-yellow. */
export function boardTexture(): THREE.CanvasTexture {
  const [c, g] = canvas(1024, 64);
  const grd = g.createLinearGradient(0, 0, 0, 64);
  grd.addColorStop(0, "#1a1f2a");
  grd.addColorStop(1, "#0d1016");
  g.fillStyle = grd;
  g.fillRect(0, 0, c.width, c.height);
  g.font = "700 38px 'Barlow Condensed', 'Barlow', sans-serif";
  g.textBaseline = "middle";
  g.fillStyle = "#ffd23f";
  g.fillText("CHALKTALK", 40, 34);
  g.fillStyle = "#f3efe3";
  g.fillText("SYNTHETIC MATCH", 560, 34);
  const t = texture(c);
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

/** A goal net mesh: a white grid on transparent. */
export function netTexture(): THREE.CanvasTexture {
  const [c, g] = canvas(64, 64);
  g.strokeStyle = "rgba(255,255,255,0.75)";
  g.lineWidth = 2;
  g.strokeRect(0, 0, 64, 64);
  const t = texture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

/** A soft round contact shadow, dark in the middle. */
export function shadowTexture(): THREE.CanvasTexture {
  const [c, g] = canvas(64, 64);
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, "rgba(0,0,0,0.55)");
  grd.addColorStop(0.5, "rgba(0,0,0,0.28)");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 64);
  return texture(c);
}

/** Pitch markings as flat ribbons (crisp at any distance, unlike 1 px GL lines). */
export function markingsGeometry(width = 0.12): THREE.BufferGeometry {
  const pos: number[] = [];
  const h = width / 2;
  const seg = (x1: number, y1: number, x2: number, y2: number) => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    // Extend each end by half a width so corners close.
    const [ux, uy] = [(dx / len) * h, (dy / len) * h];
    const [nx, ny] = [-uy, ux];
    const a = [x1 - ux + nx, y1 - uy + ny];
    const b = [x1 - ux - nx, y1 - uy - ny];
    const c = [x2 + ux - nx, y2 + uy - ny];
    const d = [x2 + ux + nx, y2 + uy + ny];
    for (const [x, y] of [a, b, c, a, c, d]) pos.push(x, 0, -y);
  };
  const rect = (x: number, y: number, w: number, hh: number) => {
    seg(x, y, x + w, y);
    seg(x + w, y, x + w, y + hh);
    seg(x + w, y + hh, x, y + hh);
    seg(x, y + hh, x, y);
  };
  const arc = (cx: number, cy: number, r: number, a0: number, a1: number, n = 64) => {
    for (let k = 0; k < n; k++) {
      const a = a0 + ((a1 - a0) * k) / n;
      const b = a0 + ((a1 - a0) * (k + 1)) / n;
      seg(cx + r * Math.cos(a), cy + r * Math.sin(a), cx + r * Math.cos(b), cy + r * Math.sin(b));
    }
  };
  const spot = (x: number, y: number) => arc(x, y, 0.1, 0, 2 * Math.PI, 8);
  rect(-HALF_L, -HALF_W, 2 * HALF_L, 2 * HALF_W);
  seg(0, -HALF_W, 0, HALF_W);
  arc(0, 0, 9.15, 0, 2 * Math.PI, 96);
  spot(0, 0);
  for (const d of [1, -1]) {
    const gx = d * HALF_L;
    rect(d === 1 ? gx - 16.5 : gx, -20.16, 16.5, 40.32);
    rect(d === 1 ? gx - 5.5 : gx, -9.16, 5.5, 18.32);
    const a = Math.acos(5.5 / 9.15);
    arc(d * (HALF_L - 11), 0, 9.15, d === 1 ? Math.PI - a : -a, d === 1 ? Math.PI + a : a, 24);
    spot(d * (HALF_L - 11), 0);
    // Corner arcs.
    for (const s of [1, -1]) arc(gx, s * HALF_W, 1, d === 1 ? (s === 1 ? Math.PI : Math.PI / 2) : s === 1 ? -Math.PI / 2 : 0, d === 1 ? (s === 1 ? 1.5 * Math.PI : Math.PI) : s === 1 ? 0 : Math.PI / 2, 8);
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
}
