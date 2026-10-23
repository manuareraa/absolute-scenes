import { useEffect, useState, type ReactNode } from "react";
import type { Frame } from "@chalktalk/contracts";
import { HALF_L, HALF_W, VIEW_BOX, toSvg } from "../pitch";

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

export function PitchView({ frame, children, label = "Synthetic pitch view" }: { frame: Frame | undefined; children?: ReactNode; label?: string }) {
  const k = usePhone() ? 1.6 : 1;
  return (
    <svg className="pitch" viewBox={VIEW_BOX} role="img" aria-label={label}>
      <rect className="grass" x={-HALF_L - 4} y={-HALF_W - 4} width={2 * HALF_L + 8} height={2 * HALF_W + 8} />
      {Array.from({ length: 10 }, (_, i) => (
        <rect key={i} className="stripe" x={-HALF_L + i * 10.5} y={-HALF_W} width={5.25} height={2 * HALF_W} />
      ))}
      <Markings />
      {children}
      {frame && (
        <g className="players">
          {frame.players.map((p) => {
            const [x, y] = toSvg([p.x, p.y]);
            const rad = (-p.heading * Math.PI) / 180;
            return (
              <g key={p.id} className={`player ${p.team}`} transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})${k === 1 ? "" : ` scale(${k})`}`}>
                <circle r={1.05} />
                <line x1={0} y1={0} x2={(1.7 * Math.cos(rad)).toFixed(2)} y2={(1.7 * Math.sin(rad)).toFixed(2)} />
                <text y={0.42}>{p.team === "ref" ? "" : p.id.slice(1)}</text>
              </g>
            );
          })}
          {/* The ball is drawn larger than life, with a ground shadow that parts from it in the air. */}
          <ellipse className="ball-shadow" cx={frame.ball.x + Math.min(frame.ball.z, 3) * 0.3} cy={-frame.ball.y + Math.min(frame.ball.z, 3) * 0.3} rx={0.9 * k} ry={0.6 * k} />
          <circle
            className="ball"
            cx={frame.ball.x}
            cy={-frame.ball.y}
            r={(0.85 + Math.min(frame.ball.z, 3) * 0.15) * k}
          />
        </g>
      )}
    </svg>
  );
}
