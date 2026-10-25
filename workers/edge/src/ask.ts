// "Ask the pundit" at the edge: POST /api/ask passes the viewer's question to the crew backend and
// streams its NDJSON (contracts/schemas/ask-event.schema.json) straight back, never buffered, so
// the Worker stays inside the free plan's 10 ms of CPU. /api/voice-token trades the Speech key (a
// Worker secret) for a 10-minute token, so the browser never holds a key.
//
//   501  no backend (or no Speech key) configured: the web app plays its labelled rehearsal feed
//   503  switched off by ASK_ENABLED=false
//   429  this viewer asked too often this minute, or the day's quota is spent
import type { Env } from "./env";
import { isMatchId } from "./routes";

export const MAX_ASK_BYTES = 4096;
export const MAX_QUESTION = 300;
/** Name of the one MatchHub instance that keeps the ask counters (not a valid match id, so no clash). */
export const QUOTA_HUB = "~ask-quota";

export type Bucket = "ask" | "voice";

export interface QuotaRequest {
  /** A hash of the viewer's IP; the raw address is never stored. */
  key: string;
  bucket: Bucket;
  perMinute: number;
  /** 0 means no daily cap for this bucket. */
  perDay: number;
}

export type QuotaAnswer = { ok: true } | { ok: false; reason: "busy" | "quota" };

const int = (v: string | undefined, fallback: number) => {
  const n = Number(v);
  return v !== undefined && Number.isInteger(n) && n >= 0 ? n : fallback;
};

export const askEnabled = (env: Env) => !/^(false|0|off|no)$/i.test(env.ASK_ENABLED ?? "");

export function limits(env: Env, bucket: Bucket): Pick<QuotaRequest, "perMinute" | "perDay"> {
  return bucket === "ask"
    ? { perMinute: int(env.ASK_PER_MINUTE, 4), perDay: int(env.ASK_DAILY_QUOTA, 300) }
    : { perMinute: int(env.VOICE_PER_MINUTE, 6), perDay: 0 };
}

/** Fixed one-minute windows per viewer; true when this request still fits. */
export function admit(windows: Map<string, { minute: number; n: number }>, key: string, now: number, perMinute: number): boolean {
  const minute = Math.floor(now / 60_000);
  // Drop windows from earlier minutes so the map stays small.
  if (windows.size > 1000) for (const [k, w] of windows) if (w.minute < minute) windows.delete(k);
  const w = windows.get(key);
  if (!w || w.minute !== minute) {
    windows.set(key, { minute, n: 1 });
    return perMinute > 0;
  }
  w.n += 1;
  return w.n <= perMinute;
}

/** The UTC day the daily quota counts against. */
export const quotaDay = (now: number) => new Date(now).toISOString().slice(0, 10);

/** A well-formed ask body, or the reason it is not. Only the fields the crew needs go through. */
export function checkAsk(body: unknown): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  if (!body || typeof body !== "object") return { ok: false, error: "bad body" };
  const b = body as Record<string, unknown>;
  if (typeof b.question !== "string" || !b.question.trim() || b.question.length > MAX_QUESTION) return { ok: false, error: "bad question" };
  if (!isMatchId(b.match_id)) return { ok: false, error: "bad match_id" };
  if (typeof b.match_tc !== "number" || !Number.isFinite(b.match_tc) || b.match_tc < 0) return { ok: false, error: "bad match_tc" };
  if (typeof b.lang !== "string" || !/^[a-z]{2}(-[A-Z]{2})?$/.test(b.lang)) return { ok: false, error: "bad lang" };
  const keep = ["question", "suggestion", "match_id", "moment_id", "match_tc", "lang", "lens", "side"];
  const out: Record<string, unknown> = {};
  for (const k of keep) if (b[k] !== undefined) out[k] = b[k];
  // The crew keys its show by show_id (any id naming the match, such as "sim-7"); the web sends match_id.
  out.show_id = out.match_id;
  for (const k of ["suggestion", "moment_id", "lens", "side"]) {
    if (out[k] !== undefined && (typeof out[k] !== "string" || (out[k] as string).length > 64)) return { ok: false, error: `bad ${k}` };
  }
  return { ok: true, body: out };
}

/** SHA-256 of the viewer's IP, shortened: enough to tell viewers apart, not to recover the address. */
export async function viewerKey(request: Request): Promise<string> {
  const ip = request.headers.get("cf-connecting-ip") ?? "local";
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`chalktalk-ask:${ip}`));
  return [...new Uint8Array(d).slice(0, 12)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

const NO_STORE = { "cache-control": "no-store" };
export const refuse = (status: number, error: string) => Response.json({ error }, { status, headers: NO_STORE });

/** Sends the checked question to the crew and streams its answer back as it comes. */
export async function proxyAsk(body: Record<string, unknown>, env: Env, signal: AbortSignal | undefined, fetchFn: typeof fetch = fetch): Promise<Response> {
  const headers: Record<string, string> = { "content-type": "application/json", accept: "application/x-ndjson" };
  if (env.ASK_BACKEND_SECRET) headers["x-chalktalk-secret"] = env.ASK_BACKEND_SECRET;
  let res: Response;
  try {
    res = await fetchFn(env.ASK_BACKEND_URL!, { method: "POST", headers, body: JSON.stringify(body), signal });
  } catch {
    return refuse(502, "backend unreachable");
  }
  if (res.status === 429) return refuse(429, "busy");
  if (!res.ok || !res.body) return refuse(502, `backend ${res.status}`);
  return new Response(res.body, {
    status: 200,
    headers: { "content-type": "application/x-ndjson; charset=utf-8", ...NO_STORE, "x-content-type-options": "nosniff" },
  });
}

/** A Speech token for the viewer's browser; the key itself never leaves the Worker. */
export async function voiceToken(env: Env, fetchFn: typeof fetch = fetch): Promise<Response> {
  const region = env.SPEECH_REGION ?? "koreacentral";
  if (!/^[a-z0-9]+$/.test(region)) return refuse(500, "bad region");
  let res: Response;
  try {
    res = await fetchFn(`https://${region}.api.cognitive.microsoft.com/sts/v1.0/issueToken`, {
      method: "POST",
      headers: { "Ocp-Apim-Subscription-Key": env.SPEECH_KEY!, "content-length": "0" },
    });
  } catch {
    return refuse(502, "speech unreachable");
  }
  if (!res.ok) return refuse(502, `speech ${res.status}`);
  return Response.json({ token: await res.text(), region, expires_in: 600 }, { headers: NO_STORE });
}
