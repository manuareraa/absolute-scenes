// End to end against workerd (through wrangler): the real Worker, the MatchHub Durable
// Object with hibernating sockets, static assets and the alarm-driven clock.
// S2 edge half: two clients on one match both receive the same frames and overlays.
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { unstable_startWorker } from "wrangler";
import { overlay, writePackage } from "./fixture";

const SECRET = "test-secret-not-real";
const MATCH = "sim-test";

type Msg = { type: string; [k: string]: any };

class Client {
  readonly messages: Msg[] = [];
  private waiters: (() => void)[] = [];
  constructor(readonly ws: WebSocket) {
    ws.addEventListener("message", (e) => {
      this.messages.push(JSON.parse(String(e.data)));
      for (const w of this.waiters.splice(0)) w();
    });
  }
  static async open(url: string): Promise<Client> {
    const ws = new WebSocket(url);
    const c = new Client(ws);
    await new Promise((ok, fail) => {
      ws.addEventListener("open", ok, { once: true });
      ws.addEventListener("error", fail, { once: true });
    });
    return c;
  }
  async next(pred: (m: Msg) => boolean, timeoutMs = 5000): Promise<Msg> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const hit = this.messages.find(pred);
      if (hit) return hit;
      if (Date.now() > deadline) throw new Error(`timed out; got ${this.messages.map((m) => m.type)}`);
      await new Promise<void>((ok) => {
        this.waiters.push(ok);
        setTimeout(ok, 100);
      });
    }
  }
  close() {
    this.ws.close();
  }
}

let worker: Awaited<ReturnType<typeof unstable_startWorker>>;
let base: URL;
let dir: string;

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "chalktalk-edge-"));
  const assets = join(dir, "public");
  writePackage(assets, MATCH, 6000);
  const config = join(dir, "wrangler.json");
  writeFileSync(
    config,
    JSON.stringify({
      name: "chalktalk-test",
      main: resolve(__dirname, "../src/index.ts"),
      compatibility_date: "2026-09-01",
      assets: {
        directory: assets,
        binding: "ASSETS",
        not_found_handling: "single-page-application",
        run_worker_first: ["/api/*", "/ws/*"],
      },
      durable_objects: { bindings: [{ name: "MATCH_HUB", class_name: "MatchHub" }] },
      migrations: [{ tag: "v1", new_sqlite_classes: ["MatchHub"] }],
      vars: { BATCH_MS: "250", OVERLAY_SECRET: SECRET },
    }),
  );
  worker = await unstable_startWorker({
    config,
    dev: { server: { hostname: "127.0.0.1", port: 0 }, inspector: false, watch: false, persist: join(dir, "state") },
  });
  base = await worker.url;
}, 60_000);

afterAll(async () => {
  await worker?.dispose();
  if (dir) rmSync(dir, { recursive: true, force: true });
});

const wsUrl = (id: string) => `${base.origin.replace(/^http/, "ws")}/ws/match/${id}`;
const post = (path: string, body: unknown, secret: string | null = SECRET) =>
  fetch(new URL(path, base), {
    method: "POST",
    headers: { "content-type": "application/json", ...(secret ? { "x-chalktalk-secret": secret } : {}) },
    body: JSON.stringify(body),
  });

describe("edge worker", () => {
  it("serves the manifest from static assets", async () => {
    const res = await fetch(new URL(`/api/match/${MATCH}`, base));
    expect(res.status).toBe(200);
    const m = (await res.json()) as any;
    expect(m.match_id).toBe(MATCH);
    expect(m.base).toBe(`/matches/${MATCH}/`);
    expect(m.ws).toBe(`/ws/match/${MATCH}`);
    expect(m.chunks.length).toBe(3);
  });

  it("404s an unknown match instead of the SPA fallback", async () => {
    expect((await fetch(new URL("/api/match/nope", base))).status).toBe(404);
  });

  it("serves chunks as static files", async () => {
    const res = await fetch(new URL(`/matches/${MATCH}/chunks/c00000.json.gz`, base));
    expect(res.status).toBe(200);
  });

  it("guards overlay posts with the shared secret", async () => {
    expect((await post("/api/overlay", { match_id: MATCH, overlay: overlay("x") }, null)).status).toBe(403);
    expect((await post("/api/overlay", { match_id: MATCH, overlay: overlay("x") }, "wrong")).status).toBe(403);
    expect((await post("/api/overlay", { match_id: MATCH, overlay: { id: "x" } })).status).toBe(400);
    const get = await fetch(new URL("/api/overlay", base));
    expect(get.status).toBe(405);
  });

  it("broadcasts frames and overlays to two clients on one match", async () => {
    const a = await Client.open(wsUrl(MATCH));
    const b = await Client.open(wsUrl(MATCH));
    try {
      const helloA = await a.next((m) => m.type === "hello");
      const helloB = await b.next((m) => m.type === "hello");
      expect(helloA.fps).toBe(25);
      expect(helloB.viewers).toBe(2);
      expect(helloB.clock.playing).toBe(true);

      // Both get batched frames from the running clock, in order and at 25 fps spacing.
      const fa = await a.next((m) => m.type === "frames" && m.frames.length > 0);
      const fb = await b.next((m) => m.type === "frames" && m.frames.length > 0);
      for (const f of [fa, fb]) {
        expect(f.t1).toBeGreaterThan(f.t0);
        for (const fr of f.frames) expect(fr.t).toBeGreaterThanOrEqual(f.t0);
        const ts = f.frames.map((x: any) => x.t);
        for (let i = 1; i < ts.length; i++) expect(ts[i] - ts[i - 1]).toBe(40);
      }

      // The clock moves on between batches.
      const later = await a.next((m) => m.type === "frames" && m.t0 > fa.t0);
      expect(later.t0).toBeGreaterThan(fa.t0);

      // A crew overlay reaches both sockets in the envelope the web expects.
      const res = await post("/api/overlay", { match_id: MATCH, overlay: overlay("ov-1") });
      expect(res.status).toBe(200);
      expect(((await res.json()) as any).viewers).toBe(2);
      const oa = await a.next((m) => m.type === "overlay");
      const ob = await b.next((m) => m.type === "overlay");
      expect(oa.overlay.id).toBe("ov-1");
      expect(ob).toEqual(oa);

      // A late joiner gets the stored overlay on join.
      const c = await Client.open(wsUrl(MATCH));
      expect((await c.next((m) => m.type === "overlay")).overlay.id).toBe("ov-1");
      c.close();

      // Viewers cannot inject messages for each other.
      a.ws.send(JSON.stringify({ type: "overlay", overlay: overlay("evil") }));
      await new Promise((r) => setTimeout(r, 400));
      expect(b.messages.some((m) => m.type === "overlay" && m.overlay.id === "evil")).toBe(false);
    } finally {
      a.close();
      b.close();
    }
  }, 30_000);

  it("controls the clock: pause, seek and the final whistle", async () => {
    const a = await Client.open(wsUrl(MATCH));
    try {
      await a.next((m) => m.type === "hello");
      let res = await post(`/api/match/${MATCH}/control`, { action: "pause" });
      expect(res.status).toBe(200);
      expect(((await res.json()) as any).clock.playing).toBe(false);
      expect((await post(`/api/match/${MATCH}/control`, { action: "jump" })).status).toBe(400);
      expect((await post(`/api/match/${MATCH}/control`, { action: "pause" }, null)).status).toBe(403);

      res = await post(`/api/match/${MATCH}/control`, { action: "seek", t: 5600 });
      expect(((await res.json()) as any).clock.t).toBe(5600);
      await post(`/api/match/${MATCH}/control`, { action: "play" });
      const end = await a.next((m) => m.type === "end", 5000);
      expect(end.clock.t).toBe(6000);
      expect(end.clock.playing).toBe(false);
    } finally {
      a.close();
    }
  }, 30_000);
});
