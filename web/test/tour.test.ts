import { describe, expect, it } from "vitest";
import { tr } from "../src/i18n";
import { placeCard } from "../src/Tour";

const view = { width: 1000, height: 800 };
const card = { width: 300, height: 200 };

describe("tour card", () => {
  it("sits under the target when it fits, else above, and stays on screen", () => {
    expect(placeCard({ top: 100, left: 400, width: 200, height: 100 }, card, view)).toEqual({ top: 218, left: 350 });
    expect(placeCard({ top: 500, left: 0, width: 100, height: 200 }, card, view)).toEqual({ top: 282, left: 12 });
    const big = placeCard({ top: 50, left: 0, width: 1000, height: 700 }, card, view);
    expect(big.top).toBeGreaterThanOrEqual(12);
    expect(big.top + card.height).toBeLessThanOrEqual(view.height - 12);
  });
});

describe("tour text", () => {
  it("has the same steps, on the same targets, in every language", () => {
    const en = tr("en-GB").tour.steps;
    const es = tr("es-ES").tour.steps;
    expect(es.map((st) => st.at)).toEqual(en.map((st) => st.at));
    expect(en.length).toBe(6);
    for (const st of [...en, ...es]) expect(st.title && st.body).toBeTruthy();
  });
});
