/* Generated from contracts/schemas/claim.schema.json by scripts/gen_contracts.sh. Do not edit. */

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
