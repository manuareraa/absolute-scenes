import { describe, expect, it } from "vitest";
import type { Overlay } from "@chalktalk/contracts";
import raw from "../public/fixtures/queue-sim-7.json?raw";
import { airStatus, demoOverlays, withDemo } from "../src/demo";
import type { QueueFixture } from "../src/producer";

const fx: QueueFixture = JSON.parse(raw);
const [first] = fx.overlays;
const at = (o: Overlay, state: Overlay["approval"]["state"], id = o.id): Overlay => ({ ...o, id, approval: { state, by: "p", at: null } });

describe("demo mode", () => {
  it("airs every overlay that passed the fact-check, as auto", () => {
    const demo = demoOverlays({ overlays: [first, { ...first, id: "failed", gate: { ...first.gate!, passed: false } }] });
    expect(demo.map((o) => o.id)).toEqual([first.id]);
    expect(demo[0].approval.state).toBe("auto");
    expect(demoOverlays(null)).toEqual([]);
  });

  it("gives way to a producer's decision on the same moment", () => {
    const demo = demoOverlays(fx);
    const other = demo.find((o) => o.match_tc !== first.match_tc)!;
    for (const state of ["approved", "rejected"] as const) {
      const merged = withDemo([at(first, state)], demo);
      expect(merged.filter((o) => o.match_tc === first.match_tc)).toEqual([at(first, state)]);
      expect(merged.some((o) => o.id === other.id)).toBe(true);
    }
  });

  it("keeps a pending hub post from hiding the demo, and does not air it twice", () => {
    const merged = withDemo([at(first, "pending")], demoOverlays(fx));
    expect(merged.filter((o) => o.id === first.id)).toHaveLength(1);
    expect(merged.find((o) => o.id === first.id)!.approval.state).toBe("auto");
  });

  it("tells the broadcast what is on air or next", () => {
    const o = [{ match_tc: 79_240 }, { match_tc: 184_920 }] as Overlay[];
    expect(airStatus(o, 10_000, false, false)).toEqual({ kind: "next", at: 79_240 });
    expect(airStatus(o, 100_000, false, false)).toEqual({ kind: "next", at: 184_920 });
    expect(airStatus(o, 200_000, false, false)).toEqual({ kind: "none" });
    expect(airStatus(o, 200_000, true, false)).toEqual({ kind: "on-air" });
    expect(airStatus(o, 600_000, false, true)).toEqual({ kind: "full-time" });
  });
});
