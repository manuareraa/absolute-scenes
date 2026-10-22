// A light shape check for overlays posted by the crew. Full JSON Schema validation (ajv)
// needs runtime code generation, which Workers forbid; the crew validates against the
// contract before posting, so the edge only guards against junk and oversize bodies.
export const MAX_OVERLAY_BYTES = 256 * 1024;

export interface OverlayPost {
  match_id: string;
  overlay: { id: string; [k: string]: unknown };
}

export function checkOverlay(body: unknown): string | null {
  if (!body || typeof body !== "object") return "body must be {match_id, overlay}";
  const { match_id, overlay } = body as Record<string, unknown>;
  if (typeof match_id !== "string") return "match_id missing";
  if (!overlay || typeof overlay !== "object") return "overlay missing";
  const o = overlay as Record<string, unknown>;
  if (typeof o.id !== "string" || o.id.length === 0 || o.id.length > 128) return "overlay.id missing";
  if (typeof o.match_tc !== "number") return "overlay.match_tc missing";
  if (!Array.isArray(o.strokes)) return "overlay.strokes missing";
  if (!Array.isArray(o.claims)) return "overlay.claims missing";
  if (!o.script || typeof o.script !== "object") return "overlay.script missing";
  return null;
}
