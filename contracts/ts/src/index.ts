// Shared contracts for the TypeScript side. Types are generated from contracts/schemas
// by scripts/gen_contracts.sh; the schemas are the source of truth.
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import frameSchema from "../../schemas/frame.schema.json";
import eventSchema from "../../schemas/event.schema.json";
import claimSchema from "../../schemas/claim.schema.json";
import overlaySchema from "../../schemas/overlay.schema.json";
import showSchema from "../../schemas/show.schema.json";

export type { Frame } from "./generated/frame";
export type { Event as MatchEvent } from "./generated/event";
export type { Claim } from "./generated/claim";
export type { Overlay } from "./generated/overlay";
export type { Show } from "./generated/show";

export const SCHEMA_NAMES = ["frame", "event", "claim", "overlay", "show"] as const;
export type ContractName = (typeof SCHEMA_NAMES)[number];

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
for (const s of [claimSchema, frameSchema, eventSchema, overlaySchema, showSchema]) ajv.addSchema(s);

export function validate(name: ContractName, data: unknown): { ok: boolean; errors: string[] } {
  const fn = ajv.getSchema(`${name}.schema.json`);
  if (!fn) throw new Error(`unknown contract ${name}`);
  const ok = fn(data) as boolean;
  return { ok, errors: (fn.errors ?? []).map((e) => `${e.instancePath} ${e.message}`) };
}

/** Timing rule: a stroke starts lead_ms before the word that names it, on the audio clock. */
export function strokeStartMs(
  cues: { cue_id: string; offset_ms: number }[],
  stroke: { cue_id: string; lead_ms?: number },
): number {
  const cue = cues.find((c) => c.cue_id === stroke.cue_id);
  if (!cue) throw new Error(`stroke references missing cue ${stroke.cue_id}`);
  return Math.max(0, cue.offset_ms - (stroke.lead_ms ?? 150));
}
