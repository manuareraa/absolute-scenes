// /api/ask end to end against workerd: the real Worker streams a fake crew's NDJSON through, and
// the day's quota is kept in the MatchHub Durable Object. The fake crew is a local Node server;
// nothing here calls Azure.
import { createServer, type Server } from "node:http";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { unstable_startWorker } from "wrangler";

const CREW_SECRET = "crew-secret-not-real";
let worker: Awaited<ReturnType<typeof unstable_startWorker>>;
let crew: Server;
let base: URL;
let dir: string;
const seen: { secret?: string; body: unknown }[] = [];

beforeAll(async () => {
  // A crew that sends two events a beat apart, so the test sees a real stream.
  crew = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      seen.push({ secret: req.headers["x-chalktalk-secret"] as string | undefined, body: JSON.parse(raw) });
      res.writeHead(200, { "content-type": "application/x-ndjson" });
      res.write('{"type":"step","seq":0,"t_ms":0,"agent":"director","text":"On it."}\n');
      setTimeout(() => res.end('{"type":"done","seq":1,"t_ms":50}\n'), 50);
    });
  });
  await new Promise<void>((ok) => crew.listen(0, "127.0.0.1", ok));
  const crewUrl = `http://127.0.0.1:${(crew.address() as AddressInfo).port}/ask`;

  dir = mkdtempSync(join(tmpdir(), "chalktalk-ask-"));
  mkdirSync(join(dir, "public"), { recursive: true });
  writeFileSync(join(dir, "public", "index.html"), "<!doctype html>");
  const config = join(dir, "wrangler.json");
  writeFileSync(
    config,
    JSON.stringify({
      name: "chalktalk-ask-test",
      main: resolve(__dirname, "../src/index.ts"),
      compatibility_date: "2026-09-01",
      assets: { directory: join(dir, "public"), binding: "ASSETS", run_worker_first: ["/api/*", "/ws/*"] },
      durable_objects: { bindings: [{ name: "MATCH_HUB", class_name: "MatchHub" }] },
      migrations: [{ tag: "v1", new_sqlite_classes: ["MatchHub"] }],
      vars: { ASK_BACKEND_URL: crewUrl, ASK_BACKEND_SECRET: CREW_SECRET, ASK_PER_MINUTE: "10", ASK_DAILY_QUOTA: "2" },
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
  crew?.close();
  if (dir) rmSync(dir, { recursive: true, force: true });
});

const question = { question: "What should they have done?", suggestion: "counterfactual", match_id: "sim-7", match_tc: 175400, lang: "en-GB", lens: "analyst", side: "away" };
const ask = (body: unknown) => fetch(new URL("/api/ask", base), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

describe("/api/ask", () => {
  it("turns away a bad question before it costs anything", async () => {
    expect((await ask({ ...question, match_id: "../x" })).status).toBe(400);
    expect((await fetch(new URL("/api/ask", base))).status).toBe(405);
    expect(seen).toHaveLength(0);
  });

  it("streams the crew's answer through, then stops at the day's quota", async () => {
    for (let i = 0; i < 2; i++) {
      const res = await ask(question);
      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toMatch(/ndjson/);
      const lines = (await res.text()).trim().split("\n").map((l) => JSON.parse(l));
      expect(lines.map((e) => e.type)).toEqual(["step", "done"]);
    }
    expect(seen[0]).toEqual({ secret: CREW_SECRET, body: question });
    const over = await ask(question);
    expect(over.status).toBe(429);
    expect(await over.json()).toEqual({ error: "quota" });
    expect(seen).toHaveLength(2);
  });

  it("keeps voice off while no Speech key is set", async () => {
    expect((await fetch(new URL("/api/voice-token", base))).status).toBe(501);
  });
});
