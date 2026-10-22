// VAR moment (M8): a goal under review plays as a chapter built from B's `var_offside` tool. Until
// the decision cue is spoken the graphics are provisional: an amber dashed line and a "VAR check"
// banner, as a broadcast shows a check in progress. Meta comes from `show_fixture.py`, by the
// VAR claim's output hash.
import type { Overlay } from "@chalktalk/contracts";

export interface VarMeta {
  check_t: number;
  decision_t: number;
  reason: string | null;
  /** The sim's `var_decision`: `goal_stands` or `goal_disallowed`. */
  decision: string;
  /** What the offside test found at the play. */
  offside: "offside" | "onside";
  /** The cue that reveals the decision; graphics before it are provisional. */
  decision_cue: string;
}

export type VarMap = Record<string, VarMeta>;

export const varFor = (map: VarMap | undefined, o: Overlay | null | undefined) =>
  o ? o.claims.map((c) => map?.[c.tool_call.output_hash]).find(Boolean) : undefined;

/** Provisional until the decision cue's audio time. */
export function isProvisional(meta: VarMeta, o: Overlay, audioMs: number): boolean {
  const cue = o.script.cues.find((c) => c.cue_id === meta.decision_cue);
  return cue ? audioMs < cue.offset_ms : false;
}

/** While provisional, the offside line is drawn amber and dashed. */
export function varGraphics(meta: VarMeta, o: Overlay, audioMs: number): Overlay {
  if (!isProvisional(meta, o, audioMs)) return o;
  return {
    ...o,
    strokes: o.strokes.map((s) => (s.shape === "offside_line" ? { ...s, style: { ...s.style, color: "danger", dash: true } } : s)),
  };
}

const DECISIONS: Record<string, string> = { goal_stands: "Goal stands", goal_disallowed: "No goal" };

export function varBanner(meta: VarMeta, provisional: boolean): { title: string; detail: string } {
  if (provisional) return { title: "VAR check · provisional", detail: meta.reason ? `Checking: ${meta.reason}` : "Checking" };
  return { title: `VAR · ${DECISIONS[meta.decision] ?? meta.decision.replaceAll("_", " ")}`, detail: meta.offside === "onside" ? "Onside" : "Offside" };
}
