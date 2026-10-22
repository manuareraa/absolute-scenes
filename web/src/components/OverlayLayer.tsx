import type { Frame, Overlay } from "@chalktalk/contracts";
import { HALF_W, arrowHead, pathD, toSvg, toVec, truncatePolyline, type Vec } from "../pitch";
import { strokeProgress } from "../playback";

type Stroke = Overlay["strokes"][number];

const COLORS = new Set(["chalk", "home", "away", "danger", "ghost"]);
const colorVar = (s: Stroke) => `var(--stroke-${COLORS.has(s.style?.color ?? "") ? s.style!.color : "chalk"})`;

/** Anchor of a stroke: its player's position this frame, else its first point. */
function anchor(stroke: Stroke, frame: Frame | undefined): Vec | null {
  const g = stroke.geometry_m;
  const p = g.player_id ? frame?.players.find((q) => q.id === g.player_id) : undefined;
  if (p) return [p.x, p.y];
  return g.points?.length ? toVec(g.points[0]) : null;
}

/** One stroke at draw-on progress `k` (0..1). Exported for tests. */
export function StrokeShape({ stroke, frame, k }: { stroke: Stroke; frame: Frame | undefined; k: number }) {
  const color = colorVar(stroke);
  const width = stroke.style?.width;
  const dash = stroke.style?.dash ? "1.2 0.9" : undefined;
  const pts = (stroke.geometry_m.points ?? []).map(toVec);
  const drawn = truncatePolyline(pts, k);
  const common = { "data-shape": stroke.shape, "data-stroke": stroke.id };

  switch (stroke.shape) {
    case "arrow":
    case "run":
    case "ghost_path": {
      const head = k >= 1 ? arrowHead(drawn) : null;
      const cls = stroke.shape === "ghost_path" ? "ghost" : stroke.shape;
      return (
        <g {...common} className={`stroke ${cls}`} stroke={color} fill={color}>
          <path d={pathD(drawn)} fill="none" strokeWidth={width ?? 0.45} strokeDasharray={dash ?? (stroke.shape === "run" ? "1.2 0.9" : undefined)} />
          {head && <path d={head} stroke="none" />}
          {stroke.shape === "ghost_path" && drawn.length > 0 && (
            <circle className="ghost-marker" cx={toSvg(drawn[drawn.length - 1])[0]} cy={toSvg(drawn[drawn.length - 1])[1]} r={1.05} />
          )}
        </g>
      );
    }
    case "pass_lane":
      return (
        <g {...common} className="stroke pass_lane" stroke={color}>
          <path d={pathD(drawn)} fill="none" strokeWidth={width ?? 1.2} strokeLinecap="round" opacity={0.45} />
          <path d={pathD(drawn)} fill="none" strokeWidth={0.2} />
        </g>
      );
    case "line":
      return (
        <path {...common} className="stroke line" d={pathD(drawn)} fill="none" stroke={color} strokeWidth={width ?? 0.3} strokeDasharray={dash} />
      );
    case "offside_line": {
      // A full-width line at the given x, drawn from one touchline to the other.
      const x = pts[0]?.[0] ?? 0;
      const line = truncatePolyline([[x, -HALF_W], [x, HALF_W]], k);
      return (
        <path {...common} className="stroke offside_line" d={pathD(line)} fill="none" stroke={color} strokeWidth={width ?? 0.3} strokeDasharray={dash} />
      );
    }
    case "zone": {
      const d = pts.length ? `${pathD(pts)} Z` : "";
      return <path {...common} className="stroke zone" d={d} fill={color} stroke={color} strokeWidth={0.2} fillOpacity={0.22 * k} strokeOpacity={k} />;
    }
    case "ring":
    case "spotlight": {
      const a = anchor(stroke, frame);
      if (!a) return null;
      const [cx, cy] = toSvg(a);
      const r = (stroke.geometry_m.radius ?? 2) * (stroke.shape === "ring" ? 0.6 + 0.4 * k : 1);
      return stroke.shape === "ring" ? (
        <circle {...common} className="stroke ring" cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={width ?? 0.35} opacity={k} />
      ) : (
        <circle {...common} className="stroke spotlight" cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.28 * k} stroke="none" />
      );
    }
    case "label": {
      const a = anchor(stroke, frame);
      if (!a) return null;
      const [x, y] = toSvg(a);
      const text = stroke.geometry_m.text ?? "";
      return (
        <text {...common} className="stroke label" x={x} y={y} fill={color}>
          {text.slice(0, Math.ceil(text.length * k))}
        </text>
      );
    }
  }
}

/** Every stroke of the active overlay that has started by `audioMs`. */
export function OverlayLayer({ overlay, frame, audioMs }: { overlay: Overlay | null; frame: Frame | undefined; audioMs: number }) {
  if (!overlay) return null;
  return (
    <g className="overlay">
      {overlay.strokes.map((s) => {
        const k = strokeProgress(overlay, s, audioMs);
        return k === null ? null : <StrokeShape key={s.id} stroke={s} frame={frame} k={k} />;
      })}
    </g>
  );
}
