import { describe, expect, it, vi } from "vitest";
import { validate, type Overlay } from "@chalktalk/contracts";
import raw from "../public/fixtures/queue-sim-7.json?raw";
import { frameAt } from "../src/playback";
import {
  airLabel,
  applyDecisions,
  approvalFor,
  broadcastUrl,
  byMoment,
  counts,
  gateRows,
  mergeQueue,
  momentTellings,
  nextMoment,
  postDecision,
  queueOrder,
  restartMatch,
  withdrawn,
  type QueueFixture,
} from "../src/producer";

const fx: QueueFixture = JSON.parse(raw);
const AT = new Date("2026-10-22T10:00:00Z");
const [first] = fx.overlays;
const n = fx.overlays.length;
const failed: Overlay = { ...first, id: "failed", gate: { ...first.gate!, passed: false } };

describe("queue fixture", () => {
  it("holds crew overlays that pass the overlay contract, with a frame at each moment", () => {
    const moments = new Set(fx.overlays.map((o) => o.match_tc));
    expect(moments.size).toBeGreaterThan(0);
    for (const lang of ["en-GB", "es-ES"]) expect(fx.overlays.filter((o) => o.lang === lang).length).toBe(n / 2);
    for (const o of fx.overlays) {
      expect(validate("overlay", o).errors).toEqual([]);
      expect(Math.abs(frameAt(fx.frames, o.match_tc)!.t - o.match_tc)).toBeLessThan(80);
    }
  });

  it("draws the gap arrow's two lines, as the show does", () => {
    for (const o of fx.overlays) {
      for (const s of o.strokes) {
        const c = o.claims.find((x) => s.claim_ids?.includes(x.id));
        if (s.shape !== "arrow" || c?.tool_call.name !== "line_gap") continue;
        expect(o.strokes.filter((x) => x.shape === "line" && x.id.startsWith(`${s.id}-line`))).toHaveLength(2);
      }
    }
  });
});

describe("decisions", () => {
  it("approves a gated overlay, records an override when the gate failed, and rejects", () => {
    expect(approvalFor(first, "approve", " ana ", AT)).toEqual({ state: "approved", by: "ana", at: AT.toISOString() });
    expect(approvalFor(failed, "approve", "ana", AT).state).toBe("overridden");
    expect(approvalFor({ ...first, gate: undefined }, "approve", "ana", AT).state).toBe("overridden");
    expect(approvalFor(first, "reject", "  ", AT)).toEqual({ state: "rejected", by: null, at: AT.toISOString() });
  });

  it("applies decisions by id and counts states", () => {
    const all = applyDecisions(fx.overlays, { [first.id]: approvalFor(first, "reject", "ana", AT) });
    expect(all.find((o) => o.id === first.id)!.approval.state).toBe("rejected");
    expect(fx.overlays[0].approval.state).toBe("pending");
    expect(counts(all)).toMatchObject({ pending: n - 1, rejected: 1, approved: 0 });
  });

  it("puts open overlays first, in match order, and can hide decided ones", () => {
    const all = applyDecisions(fx.overlays, { [first.id]: approvalFor(first, "approve", "ana", AT) });
    const q = queueOrder(all, false);
    expect(q[q.length - 1].id).toBe(first.id);
    const open = queueOrder(all, true);
    expect(open.length).toBe(n - 1);
    for (let i = 1; i < open.length; i++) expect(open[i].match_tc).toBeGreaterThanOrEqual(open[i - 1].match_tc);
  });

  it("lists gate scores by name", () => {
    const rows = gateRows(first);
    expect(rows.map((r) => r.name)).toEqual([...rows.map((r) => r.name)].sort());
    expect(rows.length).toBe(Object.keys(first.gate!.scores ?? {}).length);
    expect(gateRows({ ...first, gate: undefined })).toEqual([]);
  });
});

describe("hub", () => {
  it("re-posts the decided overlay, with no key", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));
    const overlay = { ...first, approval: approvalFor(first, "approve", "ana", AT) };
    expect(await postDecision(fetcher as unknown as typeof fetch, fx.match_id, overlay)).toEqual({ ok: true, status: 204 });
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/overlay");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ match_id: fx.match_id, overlay });
  });

  it("restarts the match: reset, then play", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 200 }));
    expect(await restartMatch(fetcher as unknown as typeof fetch, fx.match_id)).toEqual({ ok: true, status: 200 });
    const calls = fetcher.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([u]) => u)).toEqual([`/api/match/${fx.match_id}/control`, `/api/match/${fx.match_id}/control`]);
    expect(calls.map(([, i]) => JSON.parse(i.body as string).action)).toEqual(["reset", "play"]);
  });

  it("stops at the first refusal", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 401 }));
    expect(await restartMatch(fetcher as unknown as typeof fetch, fx.match_id)).toEqual({ ok: false, status: 401 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("approving a whole moment", () => {
  it("takes every open telling at the moment, across lens, side and language", () => {
    const at = momentTellings(fx.overlays, first);
    expect(at.length).toBe(n / new Set(fx.overlays.map((o) => o.match_tc)).size); // same tellings per moment
    expect(new Set(at.map((o) => o.lang))).toEqual(new Set(["en-GB", "es-ES"]));
    expect(at.every((o) => o.match_tc === first.match_tc)).toBe(true);
    const decided = applyDecisions(fx.overlays, { [at[1].id]: approvalFor(at[1], "reject", "ed", AT) });
    expect(momentTellings(decided, first).length).toBe(at.length - 1);
  });

  it("adds the crew's live posts to the queue once", () => {
    const live = { ...first, id: "ov-live-1" };
    expect(mergeQueue(fx.overlays, [first, live]).map((o) => o.id)).toEqual([...fx.overlays.map((o) => o.id), "ov-live-1"]);
  });

  it("withdraws an approved overlay as a valid pending one", () => {
    const back = withdrawn({ ...first, approval: approvalFor(first, "approve", "ed", AT) });
    expect(back.approval).toEqual({ state: "pending", by: null, at: null });
    expect(validate("overlay", back).errors).toEqual([]);
  });
});

describe("against the live clock", () => {
  const times = [...new Set(fx.overlays.map((o) => o.match_tc))].sort((a, b) => a - b);

  it("puts moments still ahead of the clock first, grouped by moment", () => {
    const liveT = times[1];
    const q = queueOrder(fx.overlays, true, liveT);
    expect(q[0].match_tc).toBe(times[2]);
    const groups = byMoment(q);
    expect(groups.map((g) => g.at)).toEqual([...times.slice(2), ...times.slice(0, 2)]);
    expect(groups[0].overlays.every((o) => o.match_tc === times[2])).toBe(true);
  });

  it("labels a row airs in, aired once approved, or missed when left open", () => {
    expect(airLabel(first, first.match_tc - 1500)).toEqual({ kind: "airs-in", s: 2 });
    expect(airLabel(first, first.match_tc + 1)).toEqual({ kind: "missed" });
    expect(airLabel({ ...first, approval: approvalFor(first, "approve", "p", AT) }, first.match_tc + 1)).toEqual({ kind: "aired" });
    expect(airLabel({ ...first, approval: approvalFor(first, "reject", "p", AT) }, 0)).toBeNull();
    expect(airLabel(first, null)).toBeNull();
  });

  it("finds the next moment, skipping rejected ones, and none at the end", () => {
    expect(nextMoment(fx.overlays, 0)).toBe(times[0]);
    const rejected = fx.overlays.map((o) => (o.match_tc === times[0] ? { ...o, approval: approvalFor(o, "reject", "p", AT) } : o));
    expect(nextMoment(rejected, 0)).toBe(times[1]);
    expect(nextMoment(fx.overlays, times.at(-1)!)).toBeNull();
  });

  it("links to the broadcast in the row's telling, with the demo off", () => {
    const q = new URLSearchParams(broadcastUrl(first).slice(2));
    expect(Object.fromEntries(q)).toMatchObject({ surface: "broadcast", demo: "off", lens: first.lens, side: first.side, lang: first.lang });
  });
});
