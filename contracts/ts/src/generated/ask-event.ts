/* Generated from contracts/schemas/ask-event.schema.json by scripts/gen_contracts.sh. Do not edit. */

/**
 * @minItems 2
 * @maxItems 2
 */
export type Point = [unknown, unknown];

/**
 * One line of the NDJSON stream that POST /api/ask returns. A live crew answers a viewer's question about a moment: the client shows each step in the control-room strip, then plays the overlay. Order: step/tool/verdict events in any order, then one overlay (or one refusal), then done. error may replace anything after the first line.
 */
export interface AskEvent {
  type: "step" | "tool" | "verdict" | "counterfactual" | "overlay" | "refusal" | "error" | "done";
  /**
   * 0-based position in the stream.
   */
  seq: number;
  /**
   * Milliseconds since the request started.
   */
  t_ms: number;
  agent?: "director" | "analyst" | "tactician" | "critic" | "pundit" | "verifier" | "safety";
  /**
   * step: what the agent is doing, one short line for the strip. refusal/error: the reason shown to the viewer.
   */
  text?: string;
  tool?: ToolRun;
  verdict?: Verdict;
  counterfactual?: Counterfactual;
  overlay?: Overlay;
  /**
   * type=overlay: where the client fetches the answer audio, if not played through Voice Live.
   */
  audio_url?: string;
  /**
   * type=done: true when the whole answer came from the cache.
   */
  cached?: boolean;
  /**
   * type=done: the Foundry trace id for this run.
   */
  trace_id?: string;
}
export interface ToolRun {
  /**
   * MCP tool name, e.g. line_gap.
   */
  name: string;
  args: {};
  /**
   * Result in one line, e.g. 'gap 6.4 m between lines'.
   */
  summary: string;
  ms?: number;
}
export interface Verdict {
  /**
   * The claim as the Pundit said it.
   */
  claim: string;
  ok: boolean;
  /**
   * Why it was rejected, e.g. 'tool says 6.4 m, not 8 m'.
   */
  reason?: string;
  /**
   * Rewrite round; 1 is the first draft.
   */
  round: number;
}
export interface Counterfactual {
  /**
   * The Tactician's change, e.g. 'left back holds 4 m deeper'.
   */
  proposal: string;
  /**
   * The Critic accepts only if the tools show the change helps.
   */
  accepted: boolean;
  metrics: {
    /**
     * e.g. pitch_control_box, line_gap_m, xg.
     */
    name: string;
    before: number;
    after: number;
    /**
     * Id of the tool call that measured 'after'.
     */
    tool_call?: string;
  }[];
}
/**
 * type=overlay: the answer, same contract as a show chapter (surface 'player'). Its script carries audio and word cues.
 */
export interface Overlay {
  id: string;
  /**
   * Media time in ms on the HLS stream where it plays; null until scheduled.
   */
  stream_tc?: number | null;
  /**
   * Match clock in ms of the moment explained.
   */
  match_tc: number;
  surface: "broadcast" | "player" | "show";
  claims: Claim[];
  strokes: Stroke[];
  script: Script;
  camera?: Camera;
  lens: "casual" | "analyst" | "newcomer";
  side: "home" | "away" | "neutral";
  /**
   * BCP 47 tag.
   */
  lang: string;
  approval: Approval;
  gate?: Gate;
}
/**
 * One factual statement the Pundit makes, bound to the tool call that produced its value. The Verifier re-runs the tool and checks the value within tolerance.
 */
export interface Claim {
  id: string;
  /**
   * Placeholder name in the script text, e.g. 'gap_m'.
   */
  text_slot: string;
  value: number | string | boolean;
  unit?: string | null;
  tool_call: ToolCall;
  evidence_window: EvidenceWindow;
  /**
   * Allowed absolute difference on re-run; null for qualitative claims (checked by CoVe).
   */
  tolerance?: number | null;
  /**
   * null until the Verifier has run.
   */
  verified: boolean | null;
}
export interface ToolCall {
  id: string;
  name: string;
  args: {};
  /**
   * sha256 of the canonical JSON output.
   */
  output_hash: string;
}
export interface EvidenceWindow {
  start_t: number;
  end_t: number;
}
export interface Stroke {
  id: string;
  shape:
    "arrow" | "run" | "pass_lane" | "line" | "offside_line" | "zone" | "ring" | "spotlight" | "ghost_path" | "label";
  geometry_m: Geometry;
  style?: StrokeStyle;
  cue_id: string;
  lead_ms?: number;
  duration_ms?: number;
  /**
   * Claims this stroke shows (evidence links).
   */
  claim_ids?: string[];
}
/**
 * Coordinates in pitch metres, always from tools, never from the LLM.
 */
export interface Geometry {
  points?: Point[];
  radius?: number;
  player_id?: string;
  text?: string;
}
export interface StrokeStyle {
  /**
   * Design token name, e.g. 'chalk', 'home', 'away', 'danger'.
   */
  color?: string;
  width?: number;
  dash?: boolean;
}
export interface Script {
  ssml?: string;
  text: string;
  audio_url?: string;
  cues: Cue[];
  words?: Word[];
}
export interface Cue {
  cue_id: string;
  /**
   * Audio offset of the word that names the stroke.
   */
  offset_ms: number;
}
export interface Word {
  text: string;
  offset_ms: number;
  duration_ms: number;
}
export interface Camera {
  preset?: "broadcast" | "high" | "tactical" | "behind_goal" | "player";
  target?: Point;
  zoom?: number;
}
export interface Approval {
  state: "pending" | "approved" | "rejected" | "overridden" | "auto";
  by?: string | null;
  at?: string | null;
}
export interface Gate {
  passed: boolean;
  scores?: {
    [k: string]: number;
  };
}
