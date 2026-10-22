import { describe, expect, it, vi } from "vitest";
import { validate, type Overlay } from "@chalktalk/contracts";
import raw from "../public/fixtures/queue-sim-7.json?raw";
import { frameAt } from "../src/playback";
import {
  SECRET_HEADER,
  applyDecisions,
  approvalFor,
  counts,
  gateRows,
  postDecision,
  queueOrder,
  type QueueFixture,
} from "../src/producer";

const fx: QueueFixture = JSON.parse(raw);
const AT = new Date("2026-10-22T10:00:00Z");
const [first] = fx.overlays;
const failed: Overlay = { ...first, id: "failed", gate: { ...first.gate!, passed: false } };

describe("queue fixture", () => {
  it("holds crew overlays that pass the overlay contract, with a frame at each moment", () => {
    expect(fx.overlays.length).toBe(36);
    for (const o of fx.overlays) {
      expect(validate("overlay", o).errors).toEqual([]);
      expect(Math.abs(frameAt(fx.frames, o.match_tc)!.t - o.match_tc)).toBeLessThan(80);
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
    expect(counts(all)).toMatchObject({ pending: 35, rejected: 1, approved: 0 });
  });

  it("puts open overlays first, in match order, and can hide decided ones", () => {
    const all = applyDecisions(fx.overlays, { [first.id]: approvalFor(first, "approve", "ana", AT) });
    const q = queueOrder(all, false);
    expect(q[q.length - 1].id).toBe(first.id);
    const open = queueOrder(all, true);
    expect(open.length).toBe(35);
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
  it("re-posts the decided overlay with the hub secret", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));
    const overlay = { ...first, approval: approvalFor(first, "approve", "ana", AT) };
    expect(await postDecision(fetcher as unknown as typeof fetch, fx.match_id, overlay, "s3")).toEqual({ ok: true, status: 204 });
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/overlay");
    expect((init.headers as Record<string, string>)[SECRET_HEADER]).toBe("s3");
    expect(JSON.parse(init.body as string)).toEqual({ match_id: fx.match_id, overlay });
  });
});
