// Broadcast-distance 3D view (spike S3), loaded lazily so three.js stays out of the main chunk.
// Lean procedural figures: one InstancedMesh per body part, so the whole crowd of 23 is about
// six draw calls. Lambert materials, no shadows and a capped pixel ratio unless ?quality=high.
// Pitch metres map to world as (x, y) -> (x, 0, -y), y up.
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef, type PointerEvent as RPointerEvent, type WheelEvent as RWheelEvent } from "react";
import * as THREE from "three";
import type { Frame } from "@chalktalk/contracts";
import { HALF_L, HALF_W } from "../pitch";
import { armSwing, bodyPose, footPose, stepGait, type Gait } from "./gait";

const MAX = 32;
const HIP_Y = 0.92;
const TORSO_H = 0.55;
// The sim's kits (sim/teams.py): home blue with white shorts, away red with black shorts.
const SHIRT = { home: "#3e8ef7", away: "#e5484d", ref: "#f5d90a" } as const;
const SHORTS = { home: "#f4f1e6", away: "#1b1b1b", ref: "#1b1b1b" } as const;
const UP = new THREE.Vector3(0, 1, 0);

/** Pitch markings as one LineSegments geometry, with goal frames. */
function markingsGeometry(): THREE.BufferGeometry {
  const p: number[] = [];
  const seg = (x1: number, y1: number, x2: number, y2: number, h1 = 0.02, h2 = 0.02) => p.push(x1, h1, -y1, x2, h2, -y2);
  const rect = (x: number, y: number, w: number, h: number) => {
    seg(x, y, x + w, y);
    seg(x + w, y, x + w, y + h);
    seg(x + w, y + h, x, y + h);
    seg(x, y + h, x, y);
  };
  const arc = (cx: number, r: number, a0: number, a1: number) => {
    const n = 48;
    for (let k = 0; k < n; k++) {
      const a = a0 + ((a1 - a0) * k) / n;
      const b = a0 + ((a1 - a0) * (k + 1)) / n;
      seg(cx + r * Math.cos(a), r * Math.sin(a), cx + r * Math.cos(b), r * Math.sin(b));
    }
  };
  rect(-HALF_L, -HALF_W, 2 * HALF_L, 2 * HALF_W);
  seg(0, -HALF_W, 0, HALF_W);
  arc(0, 9.15, 0, 2 * Math.PI);
  for (const d of [1, -1]) {
    const gx = d * HALF_L;
    rect(d === 1 ? gx - 16.5 : gx, -20.16, 16.5, 40.32);
    rect(d === 1 ? gx - 5.5 : gx, -9.16, 5.5, 18.32);
    const a = Math.acos(5.5 / 9.15);
    arc(d * (HALF_L - 11), 9.15, d === 1 ? Math.PI - a : -a, d === 1 ? Math.PI + a : a);
    for (const y of [-3.66, 3.66]) seg(gx, y, gx, y, 0, 2.44);
    seg(gx, -3.66, gx, 3.66, 2.44, 2.44);
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
}

function Pitch() {
  const lines = useMemo(markingsGeometry, []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow>
        <planeGeometry args={[2 * HALF_L + 16, 2 * HALF_W + 14]} />
        <meshLambertMaterial color="#2f6b3a" />
      </mesh>
      {Array.from({ length: 10 }, (_, i) => (
        <mesh key={i} rotation-x={-Math.PI / 2} position={[-HALF_L + i * 10.5 + 2.625, 0.005, 0]}>
          <planeGeometry args={[5.25, 2 * HALF_W]} />
          <meshLambertMaterial color="#2b6335" />
        </mesh>
      ))}
      <lineSegments geometry={lines}>
        <lineBasicMaterial color="#f2f2ea" />
      </lineSegments>
    </group>
  );
}

const tmp = {
  m: new THREE.Matrix4(),
  q: new THREE.Quaternion(),
  q2: new THREE.Quaternion(),
  s: new THREE.Vector3(),
  a: new THREE.Vector3(),
  b: new THREE.Vector3(),
  d: new THREE.Vector3(),
  c: new THREE.Color(),
};

/** Orient a unit cylinder (y axis, centred) from `a` to `b`. */
function limb(mesh: THREE.InstancedMesh, k: number, a: THREE.Vector3, b: THREE.Vector3, r: number) {
  tmp.d.subVectors(b, a);
  const len = tmp.d.length();
  tmp.q.setFromUnitVectors(UP, tmp.d.normalize());
  tmp.m.compose(tmp.a.copy(a).add(b).multiplyScalar(0.5), tmp.q, tmp.s.set(r, len, r));
  mesh.setMatrixAt(k, tmp.m);
}

/** Camera on a sphere around the ball's x: azimuth and elevation in radians, distance in metres. */
interface Orbit {
  az: number;
  el: number;
  r: number;
  tx: number;
}
// A raised broadcast angle from behind the near touchline that frames both touchlines.
const HOME_ORBIT = { az: 0, el: 0.62, r: 92 };

function Figures({ frame, orbit }: { frame: Frame | undefined; orbit: { current: Orbit } }) {
  const latest = useRef(frame);
  latest.current = frame;
  const gaits = useRef(new Map<string, Gait>());
  const head = useRef<THREE.InstancedMesh>(null);
  const torso = useRef<THREE.InstancedMesh>(null);
  const legs = useRef<THREE.InstancedMesh>(null);
  const arms = useRef<THREE.InstancedMesh>(null);
  const ball = useRef<THREE.Mesh>(null);
  const { camera } = useThree();

  useFrame((_, delta) => {
    const f = latest.current;
    const meshes = [head.current, torso.current, legs.current, arms.current];
    if (!f || meshes.some((m) => !m)) return;
    const [hd, ts, lg, am] = meshes as THREE.InstancedMesh[];
    const n = Math.min(MAX, f.players.length);
    for (let k = 0; k < n; k++) {
      const p = f.players[k];
      const g = stepGait(gaits.current.get(p.id), p, f.t);
      gaits.current.set(p.id, g);
      const { bob, lean } = bodyPose(g);
      const yaw = (g.bodyHeading * Math.PI) / 180;
      const fwd = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
      const left = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
      const pelvis = new THREE.Vector3(p.x, HIP_Y + bob, -p.y);
      const torsoUp = UP.clone().multiplyScalar(Math.cos(lean)).addScaledVector(fwd, Math.sin(lean));

      tmp.q.setFromAxisAngle(UP, yaw);
      tmp.q2.setFromAxisAngle(new THREE.Vector3(0, 0, 1), -lean);
      tmp.q.multiply(tmp.q2);
      tmp.m.compose(tmp.a.copy(pelvis).addScaledVector(torsoUp, TORSO_H / 2), tmp.q, tmp.s.set(1, 1, 1));
      ts.setMatrixAt(k, tmp.m);
      ts.setColorAt(k, tmp.c.set(SHIRT[p.team]));
      tmp.m.compose(tmp.a.copy(pelvis).addScaledVector(torsoUp, TORSO_H + 0.17), tmp.q, tmp.s.set(1, 1, 1));
      hd.setMatrixAt(k, tmp.m);

      // Foot 0 lands on the travel-left side; hook it to whichever hip is nearer.
      const side0 = Math.cos(((g.heading - g.bodyHeading) * Math.PI) / 180) >= 0 ? 1 : -1;
      for (const i of [0, 1]) {
        const side = i === 0 ? side0 : -side0;
        const hip = pelvis.clone().addScaledVector(left, 0.1 * side);
        const fp = footPose(g, i);
        limb(lg, 2 * k + i, hip, tmp.b.set(fp.x, fp.z + 0.04, -fp.y), 1);
        lg.setColorAt(2 * k + i, tmp.c.set(SHORTS[p.team]));
        const shoulder = pelvis.clone().addScaledVector(torsoUp, TORSO_H - 0.05).addScaledVector(left, 0.22 * side);
        const a = armSwing(g, i === 0 ? 1 : 0);
        const hand = shoulder.clone().addScaledVector(UP, -0.55 * Math.cos(a)).addScaledVector(fwd, 0.55 * Math.sin(a));
        limb(am, 2 * k + i, shoulder, hand, 1);
        am.setColorAt(2 * k + i, tmp.c.set(SHIRT[p.team]));
      }
    }
    hd.count = ts.count = n;
    lg.count = am.count = 2 * n;
    for (const m of meshes as THREE.InstancedMesh[]) {
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
    ball.current?.position.set(f.ball.x, 0.11 + f.ball.z, -f.ball.y);

    // Raised side camera that pans with the ball, eased; a drag orbits it around that point.
    const o = orbit.current;
    const tx = THREE.MathUtils.clamp(f.ball.x * 0.8, -HALF_L + 20, HALF_L - 20);
    o.tx += (tx - o.tx) * (1 - Math.exp(-delta * 1.5));
    const flat = o.r * Math.cos(o.el);
    camera.position.set(o.tx + flat * Math.sin(o.az), o.r * Math.sin(o.el), flat * Math.cos(o.az));
    camera.lookAt(o.tx, 0, 0);
  });

  const cyl = useMemo(() => new THREE.CylinderGeometry(0.075, 0.06, 1, 6), []);
  const arm = useMemo(() => new THREE.CylinderGeometry(0.05, 0.045, 1, 5), []);
  return (
    <group>
      <instancedMesh ref={torso} args={[undefined, undefined, MAX]} castShadow>
        <boxGeometry args={[0.24, TORSO_H, 0.4]} />
        <meshLambertMaterial />
      </instancedMesh>
      <instancedMesh ref={head} args={[undefined, undefined, MAX]} castShadow>
        <sphereGeometry args={[0.12, 8, 6]} />
        <meshLambertMaterial color="#b98b62" />
      </instancedMesh>
      <instancedMesh ref={legs} args={[cyl, undefined, 2 * MAX]} castShadow>
        <meshLambertMaterial />
      </instancedMesh>
      <instancedMesh ref={arms} args={[arm, undefined, 2 * MAX]} castShadow>
        <meshLambertMaterial />
      </instancedMesh>
      <mesh ref={ball} castShadow>
        <sphereGeometry args={[0.32, 12, 10]} />
        <meshLambertMaterial color="#ffffff" />
      </mesh>
    </group>
  );
}

export default function Broadcast3D(props: { frame: Frame | undefined; active: boolean; quality: "light" | "high"; label?: string }) {
  const { frame, active, quality, label = "Synthetic broadcast view" } = props;
  const high = quality === "high";
  const orbit = useRef<Orbit>({ ...HOME_ORBIT, tx: 0 });
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
    o.el = THREE.MathUtils.clamp(o.el + (e.clientY - d.y) * 0.004, 0.12, 1.45);
    drag.current = { x: e.clientX, y: e.clientY };
  };
  const onUp = () => (drag.current = null);
  const onWheel = (e: RWheelEvent) => {
    orbit.current.r = THREE.MathUtils.clamp(orbit.current.r * Math.exp(e.deltaY * 0.001), 40, 150);
  };
  // Double-click returns to the broadcast angle.
  const onReset = () => Object.assign(orbit.current, HOME_ORBIT);
  return (
    <Canvas
      className="pitch3d"
      frameloop={active ? "always" : "never"}
      dpr={[1, high ? 2 : 1.5]}
      shadows={high}
      gl={{ antialias: high, powerPreference: high ? "high-performance" : "low-power" }}
      camera={{ position: [0, 57, 73], fov: 30, near: 1, far: 400 }}
      aria-label={label}
      title={label}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      onWheel={onWheel}
      onDoubleClick={onReset}
      style={{ touchAction: "none", cursor: "grab" }}
    >
      <color attach="background" args={["#0d1410"]} />
      <hemisphereLight args={["#dfe9ff", "#24402a", 1.4]} />
      <directionalLight position={[-30, 60, 40]} intensity={1.6} castShadow={high} shadow-mapSize={[1024, 1024]}>
        <orthographicCamera attach="shadow-camera" args={[-60, 60, 40, -40, 1, 200]} />
      </directionalLight>
      <Pitch />
      <Figures frame={frame} orbit={orbit} />
    </Canvas>
  );
}
