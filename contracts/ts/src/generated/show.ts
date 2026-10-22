/* Generated from contracts/schemas/show.schema.json by scripts/gen_contracts.sh. Do not edit. */

/**
 * @minItems 2
 * @maxItems 2
 */
export type Point = [unknown, unknown];

/**
 * A post-match drawn tactical show for one team, lens and language.
 */
export interface Show {
  id: string;
  match_id: string;
  side: "home" | "away" | "neutral";
  lens: "casual" | "analyst" | "newcomer";
  lang: string;
  created_at?: string;
  /**
   * @minItems 1
   */
  segments: [Segment, ...Segment[]];
}
export interface Segment {
  chapter_title: string;
  audio_url?: string;
  overlay: Overlay;
}
/**
 * One breakdown: strokes on the pitch, each bound to a spoken cue. Timing rule: a stroke starts at script.cues[cue_id].offset_ms - lead_ms on the audio clock.
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
