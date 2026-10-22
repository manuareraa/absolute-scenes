import { describe, expect, it } from "vitest";
import { route } from "../src/routes";

describe("route", () => {
  it("serves health", () => expect(route("/api/health")).toEqual({ kind: "health" }));
  it("routes a match socket", () =>
    expect(route("/ws/match/m1")).toEqual({ kind: "match_ws", matchId: "m1" }));
  it("rejects odd match ids", () => {
    expect(route("/ws/match/../x").kind).toBe("not_found");
    expect(route("/ws/match/" + "a".repeat(65)).kind).toBe("not_found");
  });
  it("routes the manifest, control and overlay", () => {
    expect(route("/api/match/sim-7")).toEqual({ kind: "match_manifest", matchId: "sim-7" });
    expect(route("/api/match/sim-7/control")).toEqual({ kind: "match_control", matchId: "sim-7" });
    expect(route("/api/overlay")).toEqual({ kind: "overlay" });
    expect(route("/api/match/a.b").kind).toBe("not_found");
  });
  it("404s the rest", () => expect(route("/api/nope").kind).toBe("not_found"));
});
