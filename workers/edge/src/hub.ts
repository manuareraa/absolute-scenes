import { DurableObject } from "cloudflare:workers";
import { admit, quotaDay, type QuotaAnswer, type QuotaRequest } from "./ask";
import { apply, chunksFor, type ChunkRef, type Clock, ended, matchT, newClock, parseAction, pause, play, seek } from "./clock";
import type { Env } from "./env";
import { isPackageFile, packageBase } from "./routes";

interface Manifest {
  match_id: string;
  fps: number;
  duration_ms: number;
  chunks: ChunkRef[];
  events: { file: string; count: number };
}

interface TimedDoc {
  t: number;
  [k: string]: unknown;
}

const MAX_OVERLAYS = 200;
const REPLAY_OVERLAYS = 50;
const CHUNK_CACHE = 2;

/**
 * One instance per match. Replays the match package from static assets against its own
 * match clock and fans out to every viewer:
 *   hello   on join: viewers, clock, manifest summary
 *   frames  once per batch (default 1 s = 25 frames): {t0, t1, clock, frames, events}
 *   overlay whenever the crew posts one (and the last few on join)
 *   end     when the clock reaches the final whistle
 * Sockets use hibernation; the alarm ticks only while someone is watching, so an idle
 * match spends no Durable Object requests. The clock pauses when the last viewer leaves.
 */
export class MatchHub extends DurableObject<Env> {
  private manifest: Manifest | null = null;
  private events: TimedDoc[] | null = null;
  private chunkCache = new Map<number, TimedDoc[]>();

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Answered by the runtime without waking the object.
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"));
    ctx.storage.sql.exec(
      "CREATE TABLE IF NOT EXISTS overlays (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, body TEXT NOT NULL)",
    );
  }

  private get batchMs(): number {
    const n = Number(this.env.BATCH_MS ?? 1000);
    return Number.isFinite(n) && n >= 200 ? n : 1000;
  }

  private get restartMs(): number {
    const n = Number(this.env.RESTART_MS ?? 20_000);
    return Number.isFinite(n) && n >= 0 ? n : 20_000;
  }

  async fetch(request: Request): Promise<Response> {
    const matchId = request.headers.get("x-match-id");
    if (matchId) await this.ctx.storage.put("match_id", matchId);
    const path = new URL(request.url).pathname;
    try {
      if (path === "/ws") return await this.join();
      if (path === "/overlay" && request.method === "POST") return await this.postOverlay(await request.json());
      if (path === "/control" && request.method === "POST") return await this.control(await request.json());
      if (path === "/quota" && request.method === "POST") return Response.json(this.quota((await request.json()) as QuotaRequest));
    } catch (e) {
      if (e instanceof MissingPackage) return Response.json({ error: e.message }, { status: 404 });
      throw e;
    }
    return new Response("not found", { status: 404 });
  }

  // --- ask quota (only on the QUOTA_HUB instance) ------------------------------------------

  // Per-viewer minute windows live in memory: losing them on eviction only forgives a minute.
  private askWindows = new Map<string, { minute: number; n: number }>();

  /** Admits one ask or voice-token request: the viewer's minute window first, then the day's quota. */
  private quota(q: QuotaRequest): QuotaAnswer {
    const now = Date.now();
    if (!admit(this.askWindows, `${q.bucket}:${q.key}`, now, q.perMinute)) return { ok: false, reason: "busy" };
    if (!q.perDay) return { ok: true };
    const sql = this.ctx.storage.sql;
    sql.exec("CREATE TABLE IF NOT EXISTS ask_days (day TEXT PRIMARY KEY, n INTEGER NOT NULL)");
    const day = quotaDay(now);
    const used = sql.exec<{ n: number }>("SELECT n FROM ask_days WHERE day = ?", day).toArray()[0]?.n ?? 0;
    if (used >= q.perDay) return { ok: false, reason: "quota" };
    sql.exec("INSERT INTO ask_days (day, n) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET n = n + 1", day);
    sql.exec("DELETE FROM ask_days WHERE day < ?", quotaDay(now - 7 * 86_400_000));
    return { ok: true };
  }

  // --- viewers ---------------------------------------------------------------------------

  private async join(): Promise<Response> {
    const manifest = await this.loadManifest();
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.ctx.acceptWebSocket(server);

    let clock = await this.clock();
    const now = Date.now();
    // The first viewer ever kicks off; after that the clock resumes when viewers return. A
    // viewer who arrives after the final whistle starts the match again from kick-off, so a late
    // visitor never lands on a finished match with nothing moving.
    if (!clock.playing) {
      if (ended(clock, now)) {
        clock = await this.saveClock(play(seek(clock, 0, now), now));
        this.broadcast(JSON.stringify({ type: "clock", clock: this.clockMsg(clock, now) }));
      } else {
        clock = await this.saveClock(play(clock, now));
      }
    }

    server.send(
      JSON.stringify({
        type: "hello",
        viewers: this.viewers().length,
        match_id: manifest.match_id,
        fps: manifest.fps,
        duration_ms: manifest.duration_ms,
        batch_ms: this.batchMs,
        clock: this.clockMsg(clock, now),
      }),
    );
    const rows = this.ctx.storage.sql
      .exec<{ body: string }>("SELECT body FROM overlays ORDER BY seq DESC LIMIT ?", REPLAY_OVERLAYS)
      .toArray()
      .reverse();
    for (const row of rows) server.send(`{"type":"overlay","overlay":${row.body}}`);
    // A first batch right away, so a new viewer does not wait for the next tick.
    if (clock.playing) server.send(await this.batch(clock, now));
    await this.ensureAlarm();
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(_ws: WebSocket, _message: string | ArrayBuffer): Promise<void> {
    // Viewers only listen. "ping" is answered by the auto-response; anything else is dropped,
    // so a viewer cannot inject overlays for others.
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    try {
      ws.close(code, reason);
    } catch {
      // Already closed.
    }
    if (this.viewers(ws).length === 0) {
      await this.saveClock(pause(await this.clock(), Date.now()));
    }
  }

  async webSocketError(ws: WebSocket): Promise<void> {
    await this.webSocketClose(ws, 1011, "error");
  }

  private viewers(except?: WebSocket): WebSocket[] {
    return this.ctx.getWebSockets().filter((ws) => ws !== except && ws.readyState === WebSocket.OPEN);
  }

  private broadcast(message: string): void {
    for (const ws of this.viewers()) {
      try {
        ws.send(message);
      } catch {
        // A socket that died between the filter and the send; its close handler cleans up.
      }
    }
  }

  // --- clock ------------------------------------------------------------------------------

  async alarm(): Promise<void> {
    const now = Date.now();
    let clock = await this.clock();
    if (this.viewers().length === 0) {
      await this.saveClock(pause(clock, now));
      return;
    }
    if (!clock.playing) {
      // Full time, with viewers still here: kick off again (the final whistle set this alarm).
      // A producer's pause mid-match is not ended, so it stays paused.
      if (!ended(clock, now)) return;
      clock = await this.saveClock(play(seek(clock, 0, now), now));
      this.broadcast(JSON.stringify({ type: "clock", clock: this.clockMsg(clock, now) }));
    } else if (ended(clock, now)) {
      clock = await this.saveClock(pause(clock, now));
      this.broadcast(JSON.stringify({ type: "end", clock: this.clockMsg(clock, now) }));
      await this.ctx.storage.setAlarm(now + this.restartMs);
      return;
    }
    this.broadcast(await this.batch(clock, now));
    await this.ctx.storage.setAlarm(now + this.batchMs);
  }

  private async ensureAlarm(): Promise<void> {
    if ((await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now() + this.batchMs);
    }
  }

  private async control(body: unknown): Promise<Response> {
    const action = parseAction(body);
    if (!action) return Response.json({ error: "bad action" }, { status: 400 });
    const now = Date.now();
    const clock = await this.saveClock(apply(await this.clock(), action, now));
    const msg = this.clockMsg(clock, now);
    this.broadcast(JSON.stringify({ type: "clock", clock: msg }));
    if (clock.playing && this.viewers().length > 0) {
      this.broadcast(await this.batch(clock, now));
      await this.ensureAlarm();
    }
    return Response.json({ ok: true, clock: msg });
  }

  private async clock(): Promise<Clock> {
    const stored = await this.ctx.storage.get<Clock>("clock");
    if (stored) return stored;
    return newClock((await this.loadManifest()).duration_ms);
  }

  private async saveClock(c: Clock): Promise<Clock> {
    await this.ctx.storage.put("clock", c);
    return c;
  }

  private clockMsg(c: Clock, now: number) {
    return { t: matchT(c, now), playing: c.playing, rate: c.rate, server_ms: now };
  }

  // --- overlays ---------------------------------------------------------------------------

  private async postOverlay(overlay: { id: string }): Promise<Response> {
    const body = JSON.stringify(overlay);
    const sql = this.ctx.storage.sql;
    // Re-posting an id replaces it (the crew may revise a moment before air).
    sql.exec("DELETE FROM overlays WHERE id = ?", overlay.id);
    sql.exec("INSERT INTO overlays (id, body) VALUES (?, ?)", overlay.id, body);
    sql.exec(
      "DELETE FROM overlays WHERE seq NOT IN (SELECT seq FROM overlays ORDER BY seq DESC LIMIT ?)",
      MAX_OVERLAYS,
    );
    const viewers = this.viewers().length;
    this.broadcast(`{"type":"overlay","overlay":${body}}`);
    return Response.json({ ok: true, id: overlay.id, viewers });
  }

  // --- match package ------------------------------------------------------------------------

  private async batch(clock: Clock, now: number): Promise<string> {
    const manifest = await this.loadManifest();
    const t0 = matchT(clock, now);
    // A batch covers the next batch_ms of match time at the current rate.
    const t1 = Math.min(manifest.duration_ms, t0 + Math.round(this.batchMs * clock.rate));
    const frames: TimedDoc[] = [];
    for (const i of chunksFor(manifest.chunks, t0, t1)) {
      for (const f of await this.loadChunk(i)) if (f.t >= t0 && f.t < t1) frames.push(f);
    }
    const events = (await this.loadEvents()).filter((e) => e.t >= t0 && e.t < t1);
    return JSON.stringify({ type: "frames", t0, t1, clock: this.clockMsg(clock, now), frames, events });
  }

  private async asset(path: string): Promise<Response> {
    const matchId = await this.ctx.storage.get<string>("match_id");
    if (!matchId) throw new MissingPackage("hub has no match id");
    const res = await this.env.ASSETS.fetch(new Request(`https://assets${packageBase(matchId)}${path}`));
    if (!isPackageFile(res)) throw new MissingPackage(`no package file ${path} for ${matchId}`);
    return res;
  }

  private async loadManifest(): Promise<Manifest> {
    this.manifest ??= (await (await this.asset("manifest.json")).json()) as Manifest;
    return this.manifest;
  }

  private async loadEvents(): Promise<TimedDoc[]> {
    if (!this.events) {
      const m = await this.loadManifest();
      this.events = (await (await this.asset(m.events.file)).json()) as TimedDoc[];
    }
    return this.events;
  }

  private async loadChunk(i: number): Promise<TimedDoc[]> {
    const hit = this.chunkCache.get(i);
    if (hit) return hit;
    const m = await this.loadManifest();
    const res = await this.asset(m.chunks[i].file);
    // Assets serve the .json.gz bytes as they are; gunzip unless something upstream already did.
    const bytes = new Uint8Array(await res.arrayBuffer());
    const gz = bytes[0] === 0x1f && bytes[1] === 0x8b;
    const body = gz ? new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip")) : bytes;
    const frames = (await new Response(body).json()) as TimedDoc[];
    this.chunkCache.set(i, frames);
    while (this.chunkCache.size > CHUNK_CACHE) {
      this.chunkCache.delete(this.chunkCache.keys().next().value!);
    }
    return frames;
  }
}

class MissingPackage extends Error {}
