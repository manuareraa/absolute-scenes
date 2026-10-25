// The broadcast view: a high main-stand TV camera on a synthetic stadium, loaded lazily so
// three.js stays out of the main chunk. Stylised on purpose (flat-shaded figures, as analysis
// graphics are), so the synthetic match never pretends to be footage.
// - Figures: one InstancedMesh per body part (about ten draw calls for 23 players), soft blob
//   shadows instead of shadow maps, kits, skin tones, numbers and a name tag on the ball.
// - Telestrator: the board's own SVG overlay laid on the grass by a per-frame CSS homography
//   (telestrator.ts), so stroke timing is exactly the board's. Text labels stand up as tags.
// Pitch metres map to world as (x, y) -> (x, 0, -y), y up.
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef, type MutableRefObject, type PointerEvent as RPointerEvent, type WheelEvent as RWheelEvent } from "react";
import * as THREE from "three";
import type { Frame, Overlay } from "@chalktalk/contracts";
import { HALF_L, HALF_W, shirtNumber, toVec, truncatePolyline, type Vec } from "../pitch";
import { OverlayLayer } from "../components/OverlayLayer";
import { ghostPose } from "../components/Ghost";
import { strokeProgress } from "../playback";
import { armSwing, bodyPose, footPose, stepGait, type Gait } from "./gait";
import { GRASS_L, GRASS_W, boardTexture, crowdTexture, grassTexture, markingsGeometry, netTexture, shadowTexture } from "./stadium";
import { TELE_BOX, TELE_PX_PER_M, groundMatrix3d, overlayBounds, project } from "./telestrator";

const MAX = 32;
const HIP_Y = 0.92;
const TORSO_H = 0.56;
// The sim's kits (sim/teams.py): home blue with white shorts, away red with black shorts.
const SHIRT = { home: "#3e8ef7", away: "#e5484d", ref: "#f5d90a" } as const;
const SHORTS = { home: "#f4f1e6", away: "#1b1b1b", ref: "#1b1b1b" } as const;
const SOCKS = { home: "#2f6fd0", away: "#b8363b", ref: "#1b1b1b" } as const;
const SKIN = ["#f1c7a5", "#e0ac83", "#c68a5f", "#a86f48", "#8a5636", "#6b3f27"];
const GHOST = "#c9b8ff";
const UP = new THREE.Vector3(0, 1, 0);
// "My player" ring on the grass, in the signal yellow of the design system.
const SIGNAL = "#ffd23f";
// The camera: vertical field of view, and the main-stand position relative to the halfway line.
const FOV = 24;
const STAND = { h: 27, z: 74 };
const FOLLOW_M = 60;

type Team = keyof typeof SHIRT;
type Player = Frame["players"][number];

/** A counterfactual "ghost" player: a see-through figure where a player should have been. */
export interface Ghost3D {
  id: string;
  /** Pitch metres. */
  x: number;
  y: number;
  team: "home" | "away";
  /** Facing, degrees counter-clockwise from +x, as in the frame contract. */
  heading?: number;
  /** A short tag over the ghost, such as "#4 should be here". */
  label?: string;
}

const hash = (s: string) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);

const tmp = {
  m: new THREE.Matrix4(),
  q: new THREE.Quaternion(),
  q2: new THREE.Quaternion(),
  s: new THREE.Vector3(),
  a: new THREE.Vector3(),
  b: new THREE.Vector3(),
  d: new THREE.Vector3(),
  c: new THREE.Color(),
  z: new THREE.Vector3(0, 0, 1),
};

/** Orient a unit cylinder (y axis, centred) from `a` to `b`, `r` times its radius. */
function limb(mesh: THREE.InstancedMesh, k: number, a: THREE.Vector3, b: THREE.Vector3, r = 1) {
  tmp.d.subVectors(b, a);
  const len = tmp.d.length() || 1e-3;
  tmp.q.setFromUnitVectors(UP, tmp.d.normalize());
  tmp.m.compose(tmp.a.copy(a).add(b).multiplyScalar(0.5), tmp.q, tmp.s.set(r, len, r));
  mesh.setMatrixAt(k, tmp.m);
}

function Pitch({ high }: { high: boolean }) {
  const gl = useThree((s) => s.gl);
  const grass = useMemo(() => grassTexture(Math.min(high ? 8 : 4, gl.capabilities.getMaxAnisotropy())), [gl, high]);
  const lines = useMemo(() => markingsGeometry(), []);
  const crowd = useMemo(() => crowdTexture(Math.min(8, gl.capabilities.getMaxAnisotropy())), [gl]);
  const board = useMemo(boardTexture, []);
  const net = useMemo(netTexture, []);
  const boards: { pos: [number, number, number]; rot: number; len: number }[] = [
    { pos: [0, 0.45, -(HALF_W + 4)], rot: 0, len: 2 * HALF_L + 8 },
    { pos: [-(HALF_L + 5), 0.45, 0], rot: Math.PI / 2, len: 2 * HALF_W + 4 },
    { pos: [HALF_L + 5, 0.45, 0], rot: -Math.PI / 2, len: 2 * HALF_W + 4 },
  ];
  // Stands: the far side and both ends (the camera sits in the main stand, so it has none).
  const stands: { pos: [number, number, number]; rot: number; len: number }[] = [
    { pos: [0, 12, -(HALF_W + 26)], rot: 0, len: 2 * HALF_L + 60 },
    { pos: [-(HALF_L + 27), 12, 0], rot: Math.PI / 2, len: 2 * HALF_W + 60 },
    { pos: [HALF_L + 27, 12, 0], rot: -Math.PI / 2, len: 2 * HALF_W + 60 },
  ];
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={-0.03}>
        <planeGeometry args={[600, 600]} />
        <meshLambertMaterial color="#141a16" />
      </mesh>
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[GRASS_L, GRASS_W]} />
        <meshLambertMaterial map={grass} />
      </mesh>
      <mesh geometry={lines} position-y={0.012}>
        <meshBasicMaterial color="#f1f1e8" toneMapped={false} />
      </mesh>
      {boards.map((b, i) => (
        <mesh key={i} position={b.pos} rotation-y={b.rot}>
          <planeGeometry args={[b.len, 0.9]} />
          <meshBasicMaterial map={board} map-repeat={[b.len / 14.4, 1]} toneMapped={false} />
        </mesh>
      ))}
      {stands.map((s, i) => (
        // A raked bowl: the plane leans back at about 35 degrees.
        <mesh key={i} position={s.pos} rotation={[0, s.rot, 0]}>
          <group rotation-x={-0.62}>
            <mesh>
              <planeGeometry args={[s.len, 44]} />
              <meshLambertMaterial map={crowd} map-repeat={[s.len / 40, 2]} />
            </mesh>
          </group>
        </mesh>
      ))}
      {[1, -1].map((d) => (
        <Goal key={d} dir={d as 1 | -1} net={net} />
      ))}
    </group>
  );
}

/** Posts, bar and a see-through net, 7.32 x 2.44 m and 2 m deep. */
function Goal({ dir, net }: { dir: 1 | -1; net: THREE.Texture }) {
  const gx = dir * HALF_L;
  const back = gx + dir * 2;
  const side = useMemo(() => {
    const t = net.clone();
    t.repeat.set(2 / 0.15, 2.44 / 0.15);
    t.needsUpdate = true;
    return t;
  }, [net]);
  const wide = useMemo(() => {
    const t = net.clone();
    t.repeat.set(7.32 / 0.15, 2.44 / 0.15);
    t.needsUpdate = true;
    return t;
  }, [net]);
  const netMat = (map: THREE.Texture) => <meshBasicMaterial map={map} transparent opacity={0.55} side={THREE.DoubleSide} depthWrite={false} />;
  return (
    <group>
      {[-3.66, 3.66].map((y) => (
        <mesh key={y} position={[gx, 1.22, -y]}>
          <cylinderGeometry args={[0.06, 0.06, 2.44, 8]} />
          <meshLambertMaterial color="#ffffff" />
        </mesh>
      ))}
      <mesh position={[gx, 2.44, 0]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.06, 0.06, 7.44, 8]} />
        <meshLambertMaterial color="#ffffff" />
      </mesh>
      <mesh position={[back, 1.22, 0]} rotation-y={Math.PI / 2}>
        <planeGeometry args={[7.32, 2.44]} />
        {netMat(wide)}
      </mesh>
      <mesh position={[(gx + back) / 2, 2.44, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 2]}>
        <planeGeometry args={[7.32, 2]} />
        {netMat(wide)}
      </mesh>
      {[-3.66, 3.66].map((y) => (
        <mesh key={y} position={[(gx + back) / 2, 1.22, -y]}>
          <planeGeometry args={[2, 2.44]} />
          {netMat(side)}
        </mesh>
      ))}
    </group>
  );
}

interface SquadSource {
  players: readonly Player[];
  t: number;
}

/**
 * A squad of figures, one InstancedMesh per body part. `ghost` draws them see-through in one
 * colour (counterfactual players); otherwise in kit with varied skin tones.
 */
function Squad({ source, ghost = false }: { source: MutableRefObject<SquadSource | null>; ghost?: boolean }) {
  const gaits = useRef(new Map<string, Gait>());
  const refs = {
    torso: useRef<THREE.InstancedMesh>(null),
    head: useRef<THREE.InstancedMesh>(null),
    shorts: useRef<THREE.InstancedMesh>(null),
    thigh: useRef<THREE.InstancedMesh>(null),
    shin: useRef<THREE.InstancedMesh>(null),
    boot: useRef<THREE.InstancedMesh>(null),
    sleeve: useRef<THREE.InstancedMesh>(null),
    arm: useRef<THREE.InstancedMesh>(null),
    shadow: useRef<THREE.InstancedMesh>(null),
  };
  const shadowMap = useMemo(shadowTexture, []);

  useFrame(() => {
    const src = source.current;
    const m = Object.fromEntries(Object.entries(refs).map(([k, r]) => [k, r.current])) as Record<keyof typeof refs, THREE.InstancedMesh | null>;
    if (Object.values(m).some((x) => !x)) return;
    const M = m as Record<keyof typeof refs, THREE.InstancedMesh>;
    const players = src?.players ?? [];
    const n = Math.min(MAX, players.length);
    const color = (mesh: THREE.InstancedMesh, k: number, hex: string) => !ghost && mesh.setColorAt(k, tmp.c.set(hex));
    for (let k = 0; k < n; k++) {
      const p = players[k];
      const team = p.team as Team;
      const g = stepGait(gaits.current.get(p.id), p, src!.t);
      gaits.current.set(p.id, g);
      const { bob, lean } = bodyPose(g);
      const yaw = (g.bodyHeading * Math.PI) / 180;
      const fwd = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
      const left = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
      const pelvis = new THREE.Vector3(p.x, HIP_Y + bob, -p.y);
      const torsoUp = UP.clone().multiplyScalar(Math.cos(lean)).addScaledVector(fwd, Math.sin(lean));
      const skin = SKIN[hash(p.id) % SKIN.length];

      tmp.q.setFromAxisAngle(UP, yaw);
      tmp.q2.setFromAxisAngle(tmp.z, -lean);
      tmp.q.multiply(tmp.q2);
      tmp.m.compose(tmp.a.copy(pelvis).addScaledVector(torsoUp, TORSO_H / 2 - 0.02), tmp.q, tmp.s.set(0.78, 1, 1.18));
      M.torso.setMatrixAt(k, tmp.m);
      color(M.torso, k, SHIRT[team]);
      tmp.m.compose(tmp.a.copy(pelvis).addScaledVector(torsoUp, TORSO_H + 0.17), tmp.q, tmp.s.set(1, 1.08, 1));
      M.head.setMatrixAt(k, tmp.m);
      color(M.head, k, skin);
      // Contact shadow, stretched away from the floodlight.
      tmp.q.setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
      tmp.m.compose(tmp.a.set(p.x + 0.25, 0.02, -p.y + 0.15), tmp.q, tmp.s.set(1.5, 1.05, 1));
      M.shadow.setMatrixAt(k, tmp.m);

      // Foot 0 lands on the travel-left side; hook it to whichever hip is nearer.
      const side0 = Math.cos(((g.heading - g.bodyHeading) * Math.PI) / 180) >= 0 ? 1 : -1;
      for (const i of [0, 1]) {
        const j = 2 * k + i;
        const side = i === 0 ? side0 : -side0;
        const hip = pelvis.clone().addScaledVector(left, 0.1 * side);
        const fp = footPose(g, i);
        const foot = new THREE.Vector3(fp.x, fp.z + 0.06, -fp.y);
        // The knee sits a little forward of the hip-foot line, so legs bend.
        const knee = hip.clone().lerp(foot, 0.5).addScaledVector(fwd, 0.07).addScaledVector(UP, 0.02);
        limb(M.thigh, j, hip, knee);
        color(M.thigh, j, skin);
        limb(M.shorts, j, hip.clone().addScaledVector(UP, 0.06), hip.clone().lerp(knee, 0.55));
        color(M.shorts, j, SHORTS[team]);
        limb(M.shin, j, knee, foot);
        color(M.shin, j, SOCKS[team]);
        tmp.q.setFromAxisAngle(UP, yaw);
        tmp.m.compose(tmp.a.copy(foot).addScaledVector(fwd, 0.06).setY(Math.max(0.05, foot.y - 0.02)), tmp.q, tmp.s.set(1, 1, 1));
        M.boot.setMatrixAt(j, tmp.m);
        const shoulder = pelvis.clone().addScaledVector(torsoUp, TORSO_H - 0.06).addScaledVector(left, 0.21 * side);
        const a = armSwing(g, i === 0 ? 1 : 0);
        const hand = shoulder.clone().addScaledVector(UP, -0.56 * Math.cos(a)).addScaledVector(fwd, 0.56 * Math.sin(a)).addScaledVector(left, 0.05 * side);
        limb(M.arm, j, shoulder, hand);
        color(M.arm, j, skin);
        limb(M.sleeve, j, shoulder.clone().addScaledVector(UP, 0.03), shoulder.clone().lerp(hand, 0.38));
        color(M.sleeve, j, SHIRT[team]);
      }
    }
    for (const [key, mesh] of Object.entries(M)) {
      mesh.count = key === "torso" || key === "head" || key === "shadow" ? n : 2 * n;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  });

  const geo = useMemo(
    () => ({
      torso: new THREE.CapsuleGeometry(0.17, 0.26, 4, 10),
      head: new THREE.SphereGeometry(0.115, 12, 10),
      shorts: new THREE.CylinderGeometry(0.1, 0.095, 1, 8),
      thigh: new THREE.CylinderGeometry(0.075, 0.06, 1, 7),
      shin: new THREE.CylinderGeometry(0.062, 0.045, 1, 7),
      boot: new THREE.BoxGeometry(0.24, 0.08, 0.1),
      sleeve: new THREE.CylinderGeometry(0.066, 0.06, 1, 7),
      arm: new THREE.CylinderGeometry(0.045, 0.038, 1, 6),
      shadow: new THREE.PlaneGeometry(1, 1),
    }),
    [],
  );
  const mat = (fixed?: string) =>
    ghost ? (
      <meshBasicMaterial color={GHOST} transparent opacity={0.38} depthWrite={false} toneMapped={false} />
    ) : (
      <meshLambertMaterial color={fixed} />
    );
  const part = (key: Exclude<keyof typeof refs, "shadow">, count: number, fixed?: string) => (
    <instancedMesh ref={refs[key]} args={[geo[key], undefined, count]} frustumCulled={false}>
      {mat(fixed)}
    </instancedMesh>
  );
  return (
    <group>
      {part("torso", MAX)}
      {part("head", MAX)}
      {part("shorts", 2 * MAX)}
      {part("thigh", 2 * MAX)}
      {part("shin", 2 * MAX)}
      {part("boot", 2 * MAX, "#121212")}
      {part("sleeve", 2 * MAX)}
      {part("arm", 2 * MAX)}
      <instancedMesh ref={refs.shadow} args={[geo.shadow, undefined, MAX]} frustumCulled={false} renderOrder={1}>
        <meshBasicMaterial map={shadowMap} transparent opacity={ghost ? 0.4 : 1} depthWrite={false} />
      </instancedMesh>
    </group>
  );
}

/** Camera on a sphere around its target: user offsets on top of the TV camera. */
interface Orbit {
  az: number;
  el: number;
  zoom: number;
}
const HOME_ORBIT: Orbit = { az: 0, el: 0, zoom: 1 };

interface SceneProps {
  frame: Frame | undefined;
  overlay: Overlay | null;
  ghosts: readonly Ghost3D[];
  mine?: string | null;
  orbit: MutableRefObject<Orbit>;
  tele: MutableRefObject<SVGSVGElement | null>;
  tags: MutableRefObject<HTMLDivElement | null>;
}

function Scene({ frame, overlay, ghosts, mine, orbit, tele, tags }: SceneProps) {
  const latest = useRef({ frame, overlay, mine });
  latest.current = { frame, overlay, mine };
  const squad = useRef<SquadSource | null>(null);
  squad.current = frame ? { players: frame.players, t: frame.t } : null;
  const ghostSquad = useRef<SquadSource | null>(null);
  ghostSquad.current = {
    t: frame?.t ?? 0,
    players: ghosts.map((g) => ({ id: g.id, team: g.team, x: g.x, y: g.y, v: 0, heading: g.heading ?? 0, body_heading: g.heading ?? 0 }) as unknown as Player),
  };
  const ring = useRef<THREE.Mesh>(null);
  const ball = useRef<THREE.Mesh>(null);
  const ballShadow = useRef<THREE.Mesh>(null);
  const cam = useRef({ tx: 0, tz: 0, dist: FOLLOW_M, init: false });
  const vp = useMemo(() => new THREE.Matrix4(), []);
  const { camera, size } = useThree();
  const shadowMap = useMemo(shadowTexture, []);

  useFrame((_, delta) => {
    const { frame: f, overlay: ov, mine: me } = latest.current;
    if (f) {
      ball.current?.position.set(f.ball.x, 0.2 + f.ball.z, -f.ball.y);
      if (ballShadow.current) {
        const s = 0.9 / (1 + f.ball.z * 0.15);
        ballShadow.current.position.set(f.ball.x + 0.2 + f.ball.z * 0.25, 0.02, -f.ball.y + 0.1 + f.ball.z * 0.15);
        ballShadow.current.scale.set(s, s, 1);
      }
      const p = me ? f.players.find((q) => q.id === me) : undefined;
      if (ring.current) {
        ring.current.visible = !!p;
        if (p) ring.current.position.set(p.x, 0.03, -p.y);
      }
    }

    // The TV camera: from the main stand it follows the ball; during a breakdown it frames the
    // strokes, as a director cuts to the analysis.
    const c = cam.current;
    const persp = camera as THREE.PerspectiveCamera;
    const at = (id: string): Vec | undefined => {
      const q = f?.players.find((pl) => pl.id === id);
      return q ? [q.x, q.y] : undefined;
    };
    const box = overlayBounds(ov, at);
    let tx = THREE.MathUtils.clamp(f?.ball.x ?? 0, -HALF_L + 14, HALF_L - 14);
    let ty = THREE.MathUtils.clamp((f?.ball.y ?? 0) * 0.5, -10, 10);
    let dist = FOLLOW_M;
    if (box) {
      tx = THREE.MathUtils.clamp((box.min[0] + box.max[0]) / 2, -HALF_L + 10, HALF_L - 10);
      ty = THREE.MathUtils.clamp((box.min[1] + box.max[1]) / 2, -HALF_W + 8, HALF_W - 8);
      const vfov = THREE.MathUtils.degToRad(persp.fov) / 2;
      const hfov = Math.atan(Math.tan(vfov) * persp.aspect);
      const w = Math.max(box.max[0] - box.min[0], 12) + 16;
      const d = Math.max(box.max[1] - box.min[1], 8) + 10;
      dist = THREE.MathUtils.clamp(Math.max(w / 2 / Math.tan(hfov), (d * 0.42) / Math.tan(vfov)), 42, 125);
    }
    const ease = c.init ? 1 - Math.exp(-delta * (box ? 2.2 : 1.4)) : 1;
    c.init = true;
    c.tx += (tx - c.tx) * ease;
    c.tz += (-ty - c.tz) * ease;
    c.dist += (dist - c.dist) * ease;
    const o = orbit.current;
    const target = tmp.b.set(c.tx, 0, c.tz);
    // A fixed camera on the halfway line, a dolly along the stand, pans to the target.
    const v = new THREE.Vector3(c.tx * 0.55, STAND.h, STAND.z).sub(target);
    const sph = new THREE.Spherical().setFromVector3(v);
    sph.theta += o.az;
    sph.phi = THREE.MathUtils.clamp(sph.phi - o.el, 0.12, 1.45);
    sph.radius = c.dist * o.zoom;
    camera.position.setFromSpherical(sph).add(target);
    camera.lookAt(target);
    camera.updateMatrixWorld();

    // Lay the telestrator on the grass and stand the tags up over their players.
    vp.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    const e = vp.elements;
    if (tele.current) tele.current.style.transform = `matrix3d(${groundMatrix3d(e, size.width, size.height).map((x) => +x.toPrecision(9)).join(",")})`;
    const layer = tags.current;
    if (layer && f) {
      for (const el of Array.from(layer.children) as HTMLElement[]) {
        const pid = el.dataset.pid;
        let x: number;
        let y: number;
        let h = Number(el.dataset.gh ?? 0);
        if (pid) {
          const q = f.players.find((pl) => pl.id === pid) ?? ghostSquad.current?.players.find((pl) => pl.id === pid);
          if (!q) {
            el.style.visibility = "hidden";
            continue;
          }
          [x, y] = [q.x, q.y];
          h = 2.15;
        } else {
          [x, y] = [Number(el.dataset.gx), Number(el.dataset.gy)];
        }
        const s = project(e, size.width, size.height, [x, h, -y]);
        const on = !!s && s[0] > -60 && s[0] < size.width + 60 && s[1] > -40 && s[1] < size.height + 40;
        el.style.visibility = on ? "visible" : "hidden";
        if (s) el.style.transform = `translate(${s[0].toFixed(1)}px, ${s[1].toFixed(1)}px)`;
      }
    }
  });

  return (
    <>
      <Squad source={squad} />
      {ghosts.length > 0 && <Squad source={ghostSquad} ghost />}
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[0.75, 1.05, 32]} />
        <meshBasicMaterial color={SIGNAL} transparent opacity={0.9} depthWrite={false} toneMapped={false} />
      </mesh>
      {ghosts.map((g) => (
        <mesh key={g.id} rotation={[-Math.PI / 2, 0, 0]} position={[g.x, 0.03, -g.y]}>
          <ringGeometry args={[0.7, 0.85, 32]} />
          <meshBasicMaterial color={GHOST} transparent opacity={0.8} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
      <mesh ref={ballShadow} rotation={[-Math.PI / 2, 0, 0]} renderOrder={1}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={shadowMap} transparent depthWrite={false} />
      </mesh>
      <mesh ref={ball}>
        <sphereGeometry args={[0.2, 16, 12]} />
        <meshLambertMaterial color="#ffffff" emissive="#555555" />
      </mesh>
    </>
  );
}

export interface Broadcast3DProps {
  frame: Frame | undefined;
  active: boolean;
  quality: "light" | "high";
  label?: string;
  mine?: string | null;
  /** The breakdown to draw on the grass (the board's overlay, same timing). */
  overlay?: Overlay | null;
  audioMs?: number;
  /** A display name for a player id, e.g. "#9 Okafor". */
  nameOf?(id: string): string;
  /** Tapping a player's tag picks (or drops) that player. */
  onPick?(id: string): void;
  /** Counterfactual players, drawn see-through with a ground ring. */
  ghosts?: readonly Ghost3D[];
}

const NO_GHOSTS: readonly Ghost3D[] = [];

export default function Broadcast3D(props: Broadcast3DProps) {
  const { frame, active, quality, label = "Synthetic broadcast view", mine, overlay = null, audioMs = Infinity, nameOf, onPick } = props;
  // A ghost_path's ghost stands up as a see-through figure where the board draws its disc.
  const pathGhosts: Ghost3D[] = overlay
    ? overlay.strokes.flatMap((st) => {
        if (st.shape !== "ghost_path") return [];
        const k = strokeProgress(overlay, st, audioMs);
        if (k === null) return [];
        const pose = ghostPose(st, frame, truncatePolyline((st.geometry_m.points ?? []).map(toVec), k), k);
        if (!pose) return [];
        const team = pose.actual?.team === "away" ? "away" : "home";
        return [{ id: `ghost-${st.id}`, x: pose.at[0], y: pose.at[1], team, label: pose.actual?.label ? `#${pose.actual.label}` : undefined }];
      })
    : [];
  const ghosts = pathGhosts.length ? [...(props.ghosts ?? []), ...pathGhosts] : (props.ghosts ?? NO_GHOSTS);
  const high = quality === "high";
  const orbit = useRef<Orbit>({ ...HOME_ORBIT });
  const tele = useRef<SVGSVGElement | null>(null);
  const tags = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const onDown = (e: RPointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const o = orbit.current;
    o.az = THREE.MathUtils.clamp(o.az - (e.clientX - d.x) * 0.006, -1.4, 1.4);
    o.el = THREE.MathUtils.clamp(o.el + (e.clientY - d.y) * 0.004, -0.4, 1.1);
    drag.current = { x: e.clientX, y: e.clientY };
  };
  const onUp = () => (drag.current = null);
  const onWheel = (e: RWheelEvent) => {
    orbit.current.zoom = THREE.MathUtils.clamp(orbit.current.zoom * Math.exp(e.deltaY * 0.001), 0.45, 2);
  };
  // Double-click returns to the TV angle.
  const onReset = () => Object.assign(orbit.current, HOME_ORBIT);

  // The player on the ball (nearest, within 2.5 m) carries a name tag, as on a broadcast.
  const onBall = useMemo(() => {
    if (!frame) return null;
    let best: Player | null = null;
    let bd = 2.5;
    for (const p of frame.players) {
      if (p.team === "ref") continue;
      const d = Math.hypot(p.x - frame.ball.x, p.y - frame.ball.y);
      if (d < bd) [best, bd] = [p, d];
    }
    return best?.id ?? null;
  }, [frame]);
  // Labels stand up as tags over their anchors instead of lying flat on the grass.
  const labels = overlay
    ? overlay.strokes.flatMap((st) => {
        if (st.shape !== "label") return [];
        const k = strokeProgress(overlay, st, audioMs);
        if (k === null) return [];
        const g = st.geometry_m;
        const p = g.player_id ? frame?.players.find((q) => q.id === g.player_id) : undefined;
        const at = p ? [p.x, p.y] : g.points?.length ? [Number(g.points[0][0]), Number(g.points[0][1])] : null;
        if (!at) return [];
        const text = g.text ?? "";
        return [{ id: st.id, at, color: ["chalk", "home", "away", "danger", "ghost"].includes(st.style?.color ?? "") ? st.style!.color : "chalk", text: text.slice(0, Math.ceil(text.length * k)), lift: p ? 2.9 : 0.4 }];
      })
    : [];
  return (
    <div className={`b3${overlay ? " on-air" : ""}`} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onWheel={onWheel} onDoubleClick={onReset}>
      <Canvas
        className="pitch3d"
        frameloop={active ? "always" : "never"}
        dpr={[1, high ? 2 : 1.5]}
        gl={{ antialias: true, powerPreference: high ? "high-performance" : "default" }}
        camera={{ position: [0, STAND.h, STAND.z], fov: FOV, near: 1, far: 600 }}
        aria-label={label}
        title={label}
      >
        <color attach="background" args={["#0b0f0d"]} />
        <fog attach="fog" args={["#0b0f0d", 140, 320]} />
        <hemisphereLight args={["#e6eeff", "#2a3a2c", 1.25]} />
        <directionalLight position={[-40, 70, 30]} intensity={1.7} />
        <directionalLight position={[50, 40, -40]} intensity={0.45} color="#cfe0ff" />
        <Pitch high={high} />
        <Scene frame={frame} overlay={overlay} ghosts={ghosts} mine={mine} orbit={orbit} tele={tele} tags={tags} />
      </Canvas>
      <svg
        ref={tele}
        className="b3-tele"
        width={TELE_BOX.w * TELE_PX_PER_M}
        height={TELE_BOX.h * TELE_PX_PER_M}
        viewBox={`${TELE_BOX.x} ${TELE_BOX.y} ${TELE_BOX.w} ${TELE_BOX.h}`}
        aria-hidden="true"
      >
        <defs>
          {/* A colour-true glow: the stroke's own blur under it, as a telestrator pen reads on air. */}
          <filter id="b3-glow" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="0.45" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <g filter="url(#b3-glow)">
          <OverlayLayer overlay={overlay} frame={frame} audioMs={audioMs} />
        </g>
      </svg>
      <div ref={tags} className="b3-tags">
        {frame?.players.map((p) => {
          if (p.team === "ref") return null;
          const n = shirtNumber(p.id);
          const named = p.id === onBall || p.id === mine;
          return (
            <button
              key={p.id}
              type="button"
              data-pid={p.id}
              className={`b3-tag ${p.team}${named ? " named" : ""}${p.id === mine ? " mine" : ""}`}
              onClick={onPick ? () => onPick(p.id) : undefined}
              onPointerDown={(e) => e.stopPropagation()}
              tabIndex={onPick ? 0 : -1}
              aria-label={nameOf?.(p.id) ?? `#${n ?? p.id}`}
            >
              <span className="n">{n ?? ""}</span>
              {named && <span className="nm">{(nameOf?.(p.id) ?? "").replace(/^#\d+\s*/, "") || (p.team === "home" ? "Home" : "Away")}</span>}
            </button>
          );
        })}
        {ghosts.map((g) =>
          g.label ? (
            <span key={`g-${g.id}`} data-pid={g.id} className="b3-tag ghost named">
              <span className="nm">{g.label}</span>
            </span>
          ) : null,
        )}
        {labels.map((l) => (
          <span key={l.id} data-gx={l.at[0]} data-gy={l.at[1]} data-gh={l.lift} className={`b3-label c-${l.color}`}>
            {l.text}
          </span>
        ))}
      </div>
    </div>
  );
}
