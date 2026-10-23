import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

// Read from disk: vitest's CSS handling empties a `?raw` stylesheet import.
const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = read("../src/styles.css");
const fig = read("../src/figures/Broadcast3D.tsx");

const token = (name: string) => new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`, "i").exec(css)?.[1];
const shirt = (team: string) => new RegExp(`SHIRT = \\{[^}]*${team}: "(#[0-9a-f]{6})"`, "i").exec(fig)?.[1];

describe("team kits", () => {
  it("home is blue and away is red, as in the sim's clubs", () => {
    const [h, a] = [token("home")!, token("away")!];
    const blue = (hex: string) => parseInt(hex.slice(5, 7), 16) > parseInt(hex.slice(1, 3), 16);
    expect(blue(h)).toBe(true);
    expect(blue(a)).toBe(false);
  });

  it("the 2D board, legend and 3D figures use the same shirt colours", () => {
    expect(shirt("home")).toBe(token("home"));
    expect(shirt("away")).toBe(token("away"));
  });
});
