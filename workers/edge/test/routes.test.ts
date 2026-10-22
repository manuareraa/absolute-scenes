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
  it("404s the rest", () => expect(route("/api/nope").kind).toBe("not_found"));
});
