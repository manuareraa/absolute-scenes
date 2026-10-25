import { describe, expect, it } from "vitest";
import { admit, askEnabled, checkAsk, limits, proxyAsk, quotaDay, viewerKey, voiceToken } from "../src/ask";
import type { Env } from "../src/env";
import { route } from "../src/routes";

const env = (vars: Partial<Env> = {}) => vars as Env;
const good = { question: "What should they have done?", suggestion: "counterfactual", match_id: "sim-7", match_tc: 175400, lang: "en-GB", lens: "analyst", side: "away" };

describe("ask routes", () => {
  it("routes /api/ask and /api/voice-token", () => {
    expect(route("/api/ask")).toEqual({ kind: "ask" });
    expect(route("/api/voice-token")).toEqual({ kind: "voice_token" });
  });
});

describe("checkAsk", () => {
  it("passes a good question through, keeping only the crew's fields", () => {
    const r = checkAsk({ ...good, extra: "x" });
    expect(r).toEqual({ ok: true, body: { ...good, show_id: "sim-7" } });
  });
  it("rejects what the crew should never see", () => {
    expect(checkAsk(null).ok).toBe(false);
    expect(checkAsk({ ...good, question: "  " }).ok).toBe(false);
    expect(checkAsk({ ...good, question: "x".repeat(301) }).ok).toBe(false);
    expect(checkAsk({ ...good, match_id: "../x" }).ok).toBe(false);
    expect(checkAsk({ ...good, match_tc: -1 }).ok).toBe(false);
    expect(checkAsk({ ...good, lang: "english" }).ok).toBe(false);
    expect(checkAsk({ ...good, lens: { a: 1 } }).ok).toBe(false);
  });
});

describe("limits", () => {
  it("lets a viewer ask a few times a minute, then waits for the next minute", () => {
    const w = new Map();
    const t = 1_000_000 * 60_000;
    expect([1, 2, 3, 4, 5].map(() => admit(w, "a", t, 4))).toEqual([true, true, true, true, false]);
    expect(admit(w, "b", t, 4)).toBe(true);
    expect(admit(w, "a", t + 60_000, 4)).toBe(true);
    expect(admit(new Map(), "a", t, 0)).toBe(false);
  });
  it("reads limits and the kill switch from env, with safe defaults", () => {
    expect(limits(env(), "ask")).toEqual({ perMinute: 4, perDay: 300 });
    expect(limits(env({ ASK_PER_MINUTE: "2", ASK_DAILY_QUOTA: "50" }), "ask")).toEqual({ perMinute: 2, perDay: 50 });
    expect(limits(env({ ASK_PER_MINUTE: "lots" }), "ask").perMinute).toBe(4);
    expect(limits(env(), "voice").perDay).toBe(0);
    expect(askEnabled(env())).toBe(true);
    for (const off of ["false", "0", "off", "OFF"]) expect(askEnabled(env({ ASK_ENABLED: off }))).toBe(false);
  });
  it("counts days in UTC", () => expect(quotaDay(Date.UTC(2026, 9, 25, 23, 59))).toBe("2026-10-25"));
  it("never keeps the raw address", async () => {
    const k = await viewerKey(new Request("https://x/api/ask", { headers: { "cf-connecting-ip": "203.0.113.9" } }));
    expect(k).toMatch(/^[0-9a-f]{24}$/);
    expect(k).not.toContain("203");
  });
});

describe("proxyAsk", () => {
  it("streams the backend's body through untouched, with the secret on the way out", async () => {
    let sent: RequestInit | undefined;
    let pull = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(c) {
        pull++;
        c.enqueue(new TextEncoder().encode(`{"type":"step","seq":${pull - 1},"t_ms":0}\n`));
        if (pull === 2) c.close();
      },
    });
    const fetchFn = (async (_u: string, init: RequestInit) => {
      sent = init;
      return new Response(body, { status: 200 });
    }) as unknown as typeof fetch;
    const res = await proxyAsk(good, env({ ASK_BACKEND_URL: "https://crew.test/ask", ASK_BACKEND_SECRET: "s" }), undefined, fetchFn);
    // The same stream object: nothing was read or buffered before the viewer gets it.
    expect(res.body).toBe(body);
    expect(res.headers.get("content-type")).toMatch(/ndjson/);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect((sent!.headers as Record<string, string>)["x-chalktalk-secret"]).toBe("s");
    expect(JSON.parse(sent!.body as string)).toEqual(good);
    expect((await res.text()).trim().split("\n")).toHaveLength(2);
  });
  it("maps backend trouble to statuses the web app understands", async () => {
    const reply = (status: number) => (async () => new Response("x", { status })) as unknown as typeof fetch;
    const e = env({ ASK_BACKEND_URL: "https://crew.test/ask" });
    expect((await proxyAsk(good, e, undefined, reply(429))).status).toBe(429);
    expect((await proxyAsk(good, e, undefined, reply(500))).status).toBe(502);
    const down = (async () => {
      throw new Error("down");
    }) as unknown as typeof fetch;
    expect((await proxyAsk(good, e, undefined, down)).status).toBe(502);
  });
});

describe("voiceToken", () => {
  it("trades the key for a token without returning the key", async () => {
    let url = "";
    let key = "";
    const fetchFn = (async (u: string, init: RequestInit) => {
      url = u;
      key = (init.headers as Record<string, string>)["Ocp-Apim-Subscription-Key"];
      return new Response("tok123");
    }) as unknown as typeof fetch;
    const res = await voiceToken(env({ SPEECH_KEY: "secret-key", SPEECH_REGION: "koreacentral" }), fetchFn);
    expect(url).toBe("https://koreacentral.api.cognitive.microsoft.com/sts/v1.0/issueToken");
    expect(key).toBe("secret-key");
    const text = await res.text();
    expect(JSON.parse(text)).toEqual({ token: "tok123", region: "koreacentral", expires_in: 600 });
    expect(text).not.toContain("secret-key");
    expect(res.headers.get("cache-control")).toBe("no-store");
  });
  it("refuses an odd region instead of calling out", async () => {
    expect((await voiceToken(env({ SPEECH_KEY: "k", SPEECH_REGION: "evil.com/x" }))).status).toBe(500);
  });
});
