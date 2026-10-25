import { askEnabled, checkAsk, limits, MAX_ASK_BYTES, proxyAsk, QUOTA_HUB, refuse, viewerKey, voiceToken, type Bucket, type QuotaAnswer, type QuotaRequest } from "./ask";
import { checkSecret } from "./auth";
import type { Env } from "./env";
import { OPEN_ACTIONS, openDecision, queueFile } from "./open";
import { checkOverlay, MAX_OVERLAY_BYTES } from "./overlay";
import { isMatchId, isPackageFile, packageBase, route } from "./routes";

export { MatchHub } from "./hub";
export type { Env } from "./env";

function hub(env: Env, matchId: string): DurableObjectStub {
  return env.MATCH_HUB.get(env.MATCH_HUB.idFromName(matchId));
}

/** Forward to the match's hub on an internal path; the hub learns its match id from the header. */
function toHub(env: Env, matchId: string, path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("x-match-id", matchId);
  return hub(env, matchId).fetch(new Request(`https://hub${path}`, { ...init, headers }));
}

/** One Durable Object request: this viewer's minute window and the day's quota. */
async function admitted(request: Request, env: Env, bucket: Bucket): Promise<QuotaAnswer> {
  const q: QuotaRequest = { key: await viewerKey(request), bucket, ...limits(env, bucket) };
  const res = await hub(env, QUOTA_HUB).fetch(new Request("https://hub/quota", { method: "POST", body: JSON.stringify(q) }));
  return (await res.json()) as QuotaAnswer;
}

async function readJson(request: Request): Promise<unknown | Response> {
  const len = Number(request.headers.get("content-length") ?? "0");
  if (len > MAX_OVERLAY_BYTES) return new Response("too large", { status: 413 });
  const text = await request.text();
  if (text.length > MAX_OVERLAY_BYTES) return new Response("too large", { status: 413 });
  try {
    return JSON.parse(text);
  } catch {
    return new Response("bad json", { status: 400 });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const r = route(new URL(request.url).pathname);
    switch (r.kind) {
      case "health":
        return Response.json({ ok: true, service: "chalktalk-edge" });

      case "match_ws": {
        if (request.headers.get("Upgrade") !== "websocket") {
          return new Response("expected websocket", { status: 426 });
        }
        return toHub(env, r.matchId, "/ws", { headers: request.headers });
      }

      case "match_manifest": {
        // Straight from static assets: no Durable Object request is spent on it.
        const base = packageBase(r.matchId);
        const res = await env.ASSETS.fetch(new Request(new URL(`${base}manifest.json`, request.url)));
        if (!isPackageFile(res)) return Response.json({ error: "unknown match" }, { status: 404 });
        const manifest = (await res.json()) as Record<string, unknown>;
        return Response.json(
          { ...manifest, base, ws: `/ws/match/${r.matchId}` },
          { headers: { "cache-control": "public, max-age=60" } },
        );
      }

      case "match_control":
      case "overlay": {
        if (request.method !== "POST") return new Response("method not allowed", { status: 405 });
        // The crew (with the secret) may post any overlay. Without it, the open producer may
        // only decide queued overlays and restart the match (see open.ts).
        const trusted = !!env.OVERLAY_SECRET && (await checkSecret(request, env.OVERLAY_SECRET));
        const body = await readJson(request);
        if (body instanceof Response) return body;
        if (r.kind === "match_control") {
          const action = (body as { action?: unknown } | null)?.action;
          if (!trusted && !(typeof action === "string" && OPEN_ACTIONS.has(action))) {
            return new Response("forbidden", { status: 403 });
          }
          return toHub(env, r.matchId, "/control", { method: "POST", body: JSON.stringify(body) });
        }
        const err = checkOverlay(body);
        if (err) return Response.json({ error: err }, { status: 400 });
        const { match_id, overlay } = body as { match_id: string; overlay: { id: string; approval?: unknown } };
        if (!isMatchId(match_id)) return Response.json({ error: "bad match_id" }, { status: 400 });
        if (trusted) return toHub(env, match_id, "/overlay", { method: "POST", body: JSON.stringify(overlay) });
        const res = await env.ASSETS.fetch(new Request(new URL(queueFile(match_id), request.url)));
        if (!isPackageFile(res)) return new Response("forbidden: no published queue", { status: 403 });
        const decided = openDecision(await res.json(), match_id, overlay);
        if ("error" in decided) return Response.json({ error: decided.error }, { status: 403 });
        return toHub(env, match_id, "/overlay", { method: "POST", body: JSON.stringify(decided.overlay) });
      }

      case "ask": {
        if (request.method !== "POST") return new Response("method not allowed", { status: 405 });
        if (!askEnabled(env)) return refuse(503, "off");
        if (!env.ASK_BACKEND_URL) return refuse(501, "no backend");
        const len = Number(request.headers.get("content-length") ?? "0");
        if (len > MAX_ASK_BYTES) return refuse(413, "too large");
        const text = await request.text();
        if (text.length > MAX_ASK_BYTES) return refuse(413, "too large");
        let parsed: unknown;
        try {
          parsed = JSON.parse(text);
        } catch {
          return refuse(400, "bad json");
        }
        const checked = checkAsk(parsed);
        if (!checked.ok) return refuse(400, checked.error);
        const q = await admitted(request, env, "ask");
        if (!q.ok) return refuse(429, q.reason);
        return proxyAsk(checked.body, env, request.signal);
      }

      case "voice_token": {
        if (request.method !== "GET") return new Response("method not allowed", { status: 405 });
        if (!env.SPEECH_KEY) return refuse(501, "voice off");
        const q = await admitted(request, env, "voice");
        if (!q.ok) return refuse(429, q.reason);
        return voiceToken(env);
      }

      default:
        return new Response("not found", { status: 404 });
    }
  },
} satisfies ExportedHandler<Env>;
