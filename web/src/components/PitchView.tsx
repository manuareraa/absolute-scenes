import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import type { Frame } from "@chalktalk/contracts";
import { HALF_L, HALF_W, VIEW_BOX, layoutDiscs, shirtNumber, toSvg, type Vec } from "../pitch";

/** "Be the tactician": the viewer drags players of one team, each within `max` metres. */
export interface Tactic {
  moves: Record<string, Vec>;
  max: number;
  /** At most this many players move. */
  limit: number;
  onMove(id: string, to: Vec): void;
}

/** Where the viewer wants the player: the pointer's spot, kept within `max` m of the start and on the pitch. */
export function reach(from: Vec, want: Vec, max: number): Vec {
  const [dx, dy] = [want[0] - from[0], want[1] - from[1]];
  const d = Math.hypot(dx, dy);
  const k = d > max ? max / d : 1;
  const clamp = (v: number, h: number) => Math.max(-h, Math.min(h, v));
  return [+clamp(from[0] + dx * k, HALF_L).toFixed(2), +clamp(from[1] + dy * k, HALF_W).toFixed(2)];
}

/** Static pitch markings, 105 x 68 m, in SVG units (metres, y flipped). */
function Markings() {
  const box = (dir: 1 | -1, depth: number, width: number) => (
    <rect x={dir === 1 ? HALF_L - depth : -HALF_L} y={-width / 2} width={depth} height={width} />
  );
  return (
    <g className="markings" fill="none">
      <rect x={-HALF_L} y={-HALF_W} width={2 * HALF_L} height={2 * HALF_W} />
      <line x1={0} y1={-HALF_W} x2={0} y2={HALF_W} />
      <circle r={9.15} />
      <circle r={0.3} className="spot" />
      {([1, -1] as const).map((d) => (
        <g key={d}>
          {box(d, 16.5, 40.32)}
          {box(d, 5.5, 18.32)}
          <circle cx={d * (HALF_L - 11)} r={0.3} className="spot" />
          <rect className="goal" x={d === 1 ? HALF_L : -HALF_L - 2} y={-3.66} width={2} height={7.32} />
        </g>
      ))}
    </g>
  );
}

/** True on a phone-width screen, where markers are drawn larger so they stay readable. */
function usePhone(): boolean {
  const q = typeof matchMedia === "function" ? matchMedia("(max-width: 700px)") : null;
  const [phone, setPhone] = useState(q?.matches ?? false);
  useEffect(() => {
    if (!q) return;
    const on = () => setPhone(q.matches);
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, [q?.media]);
  return phone;
}

export function PitchView(props: {
  frame: Frame | undefined;
  children?: ReactNode;
  label?: string;
  /** "My player": a ring and a name label on this player. */
  mine?: string | null;
  mineLabel?: string;
  /** Tapping a disc picks (or drops) that player. */
  onPick?(id: string): void;
  tactic?: Tactic | null;
}) {
  const { frame, children, label = "Synthetic pitch view", mine, mineLabel, tactic } = props;
  const onPick = tactic ? undefined : props.onPick;
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const moved = tactic ? Object.keys(tactic.moves) : [];
  const team = moved.length && frame ? frame.players.find((p) => p.id === moved[0])?.team : null;
  const movable = (id: string, t: string) => !!tactic && t !== "ref" && (!team || t === team) && (id in tactic.moves || moved.length < tactic.limit);
  const pitchAt = (e: PointerEvent): Vec | null => {
    const m = svg.current?.getScreenCTM();
    if (!svg.current || !m) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return [pt.x, -pt.y];
  };
  const onDrag = (e: PointerEvent) => {
    const p = drag && frame?.players.find((q) => q.id === drag);
    const at = p && pitchAt(e);
    if (p && at && tactic) tactic.onMove(p.id, reach([p.x, p.y], at, tactic.max));
  };
  const k = usePhone() ? 1.6 : 1;
  // Nudged only where discs overlap or the ball would cover a number (`layoutDiscs`).
  const at = frame && layoutDiscs(frame.players.map((p) => [p.x, p.y]), [frame.ball.x, frame.ball.y], k);
  return (
    <svg
      ref={svg}
      className={`pitch${tactic ? " tactic" : ""}${drag ? " dragging" : ""}`}
      viewBox={VIEW_BOX}
      role="img"
      aria-label={label}
      onPointerMove={drag ? onDrag : undefined}
      onPointerUp={() => setDrag(null)}
      onPointerCancel={() => setDrag(null)}>
      <rect className="grass" x={-HALF_L - 4} y={-HALF_W - 4} width={2 * HALF_L + 8} height={2 * HALF_W + 8} />
      {Array.from({ length: 10 }, (_, i) => (
        <rect key={i} className="stripe" x={-HALF_L + i * 10.5} y={-HALF_W} width={5.25} height={2 * HALF_W} />
      ))}
      <Markings />
      {children}
      {tactic && frame && (
        <g className="tactic-marks">
          {frame.players
            .filter((p) => p.id in tactic.moves || p.id === drag)
            .map((p) => {
              const [fx, fy] = toSvg([p.x, p.y]);
              const [tx, ty] = toSvg(tactic.moves[p.id] ?? [p.x, p.y]);
              return (
                <g key={p.id}>
                  <circle className="tactic-reach" cx={fx} cy={fy} r={tactic.max} />
                  <circle className={`tactic-ghost ${p.team}`} cx={fx} cy={fy} r={1.25 * k} />
                  <line className="tactic-path" x1={fx} y1={fy} x2={tx} y2={ty} />
                </g>
              );
            })}
        </g>
      )}
      {frame && at && (
        <g className="players">
          {frame.players.map((p, i) => {
            const [x, y] = toSvg(tactic?.moves[p.id] ?? at.players[i]);
            const grab = movable(p.id, p.team);
            const rad = (-p.heading * Math.PI) / 180;
            const [cx, cy] = [Math.cos(rad), Math.sin(rad)];
            const n = p.team === "ref" ? null : shirtNumber(p.id);
            return (
              <g
                key={p.id}
                className={`player ${p.team}${p.id === mine ? " mine" : ""}${onPick && p.team !== "ref" ? " pickable" : ""}${grab ? " movable" : ""}${tactic && p.id in tactic.moves ? " moved" : ""}`}
                onClick={onPick && p.team !== "ref" ? () => onPick(p.id) : undefined}
                onPointerDown={
                  grab
                    ? (e) => {
                        e.preventDefault();
                        svg.current?.setPointerCapture(e.pointerId);
                        setDrag(p.id);
                      }
                    : undefined
                }
                transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})${k === 1 ? "" : ` scale(${k})`}`}>
                {p.id === mine && <circle className="mine-ring" r={2} />}
                <circle r={1.25} />
                {/* The heading tick starts at the disc's edge, so it never crosses the number. */}
                <line x1={(1.25 * cx).toFixed(2)} y1={(1.25 * cy).toFixed(2)} x2={(2 * cx).toFixed(2)} y2={(2 * cy).toFixed(2)} />
                {n !== null && <text y={0.5}>{n}</text>}
                {p.id === mine && mineLabel && (
                  <text className="mine-label" y={-2.7}>
                    {mineLabel}
                  </text>
                )}
              </g>
            );
          })}
          {/* The ball is drawn larger than life, with a ground shadow that parts from it in the air. */}
          <ellipse className="ball-shadow" cx={at.ball[0] + Math.min(frame.ball.z, 3) * 0.3} cy={-at.ball[1] + Math.min(frame.ball.z, 3) * 0.3} rx={0.9 * k} ry={0.6 * k} />
          <circle
            className="ball"
            cx={at.ball[0]}
            cy={-at.ball[1]}
            r={(0.85 + Math.min(frame.ball.z, 3) * 0.15) * k}
          />
        </g>
      )}
    </svg>
  );
}
