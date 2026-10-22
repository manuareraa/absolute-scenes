// The "ghost": a see-through figure where a player was expected to be, tethered to where they
// really are. Until B's ghost tool lands it reads a `ghost_path` stroke: the path's last point is
// the expected position and `geometry_m.player_id` (optional) is the real player.
import type { Frame, Overlay } from "@chalktalk/contracts";
import { dist, toSvg, toVec, type Vec } from "../pitch";

type Stroke = Overlay["strokes"][number];

export interface GhostPose {
  /** Where the ghost stands now: the tip of the drawn path. */
  at: Vec;
  /** The expected position (end of the path). */
  expected: Vec;
  /** The real player this frame, when the stroke names one. */
  actual: { at: Vec; team: string; label: string } | null;
  /** Metres between the real player and the expected position, once the path is fully drawn. */
  gapM: number | null;
}

/** Where to draw the ghost for `drawn` (the path drawn so far at progress `k`). */
export function ghostPose(stroke: Stroke, frame: Frame | undefined, drawn: Vec[], k: number): GhostPose | null {
  const pts = (stroke.geometry_m.points ?? []).map(toVec);
  if (!pts.length || !drawn.length) return null;
  const expected = pts[pts.length - 1];
  const id = stroke.geometry_m.player_id;
  const p = id ? frame?.players.find((q) => q.id === id) : undefined;
  const actual = p ? { at: [p.x, p.y] as Vec, team: p.team, label: p.team === "ref" ? "" : p.id.slice(1) } : null;
  return { at: drawn[drawn.length - 1], expected, actual, gapM: actual && k >= 1 ? dist(actual.at, expected) : null };
}

export function GhostFigure({ pose, color }: { pose: GhostPose; color: string }) {
  const [x, y] = toSvg(pose.at);
  const team = pose.actual?.team ?? "ghost";
  return (
    <g className="ghost-figure" data-ghost={team}>
      {pose.actual && pose.gapM !== null && <Tether from={pose.actual.at} to={pose.expected} gapM={pose.gapM} color={color} />}
      <g className={`ghost-body ${team}`} transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})`}>
        <circle r={1.05} stroke={color} />
        {pose.actual?.label && <text y={0.42}>{pose.actual.label}</text>}
      </g>
    </g>
  );
}

function Tether({ from, to, gapM, color }: { from: Vec; to: Vec; gapM: number; color: string }) {
  const [x1, y1] = toSvg(from);
  const [x2, y2] = toSvg(to);
  return (
    <g className="ghost-tether" stroke={color}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} />
      <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 0.8} fill={color} stroke="none">
        {gapM.toFixed(1)} m
      </text>
    </g>
  );
}
