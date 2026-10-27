import { describe, expect, it } from "vitest";
import { reach } from "../src/components/PitchView";

describe("Be the tactician: reach", () => {
  it("keeps a drag within 10 m of where the player stood", () => {
    expect(reach([0, 0], [3, 4], 10)).toEqual([3, 4]);
    expect(reach([0, 0], [30, 40], 10)).toEqual([6, 8]);
  });
  it("keeps the player on the pitch", () => {
    expect(reach([50, 30], [58, 37], 10)).toEqual([52.5, 34]);
  });
});
