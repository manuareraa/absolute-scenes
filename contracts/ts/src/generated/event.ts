/* Generated from contracts/schemas/event.schema.json by scripts/gen_contracts.sh. Do not edit. */

/**
 * A match event, from the simulator (ground truth) or detected from video.
 */
export interface Event {
  id: string;
  /**
   * Match clock in ms.
   */
  t: number;
  type:
    | "kickoff"
    | "pass"
    | "carry"
    | "dribble"
    | "shot"
    | "save"
    | "goal"
    | "tackle"
    | "interception"
    | "clearance"
    | "press"
    | "foul"
    | "card"
    | "offside"
    | "ball_out"
    | "throw_in"
    | "goal_kick"
    | "corner"
    | "free_kick"
    | "penalty"
    | "substitution"
    | "var_check"
    | "var_decision"
    | "period_end";
  /**
   * Player ids; the first is the main actor.
   */
  actors: string[];
  team?: "home" | "away";
  /**
   * Type-specific details, e.g. pass end point, outcome, xG.
   */
  attrs?: {};
  source: "sim" | "video";
  confidence: number;
}
