import { describe, expect, it } from "vitest";
import { validate } from "@chalktalk/contracts";
import raw from "../public/fixtures/show-sim-7.json?raw";
import { claimForWord, claimWords, evidenceFor } from "../src/evidence";
import { selectOverlays } from "../src/playback";
import { langsOf, pickShow, type ShowFixture } from "../src/show";

const fx: ShowFixture = JSON.parse(raw);
const es = fx.shows.filter((s) => s.lang === "es-ES");

describe("caption languages", () => {
  it("has an es-ES show for every en-GB one, with Spanish ghost and VAR chapters", () => {
    expect(langsOf(fx.shows)).toEqual(["en-GB", "es-ES"]);
    expect(es.length).toBe(fx.shows.filter((s) => s.lang === "en-GB").length);
    for (const s of es)
      for (const g of s.segments) {
        expect(g.overlay.lang, g.overlay.id).toBe("es-ES");
        expect(validate("overlay", g.overlay).errors, g.overlay.id).toEqual([]);
      }
    const titles = es[0].segments.map((g) => g.chapter_title);
    expect(titles).toContain("Dónde debía estar");
    expect(titles).toContain("Revisión del VAR: ¿fuera de juego?");
  });

  it("picks the show in the caption language, falling back to en-GB", () => {
    expect(pickShow(fx.shows, "analyst", "away", "es-ES")!.id).toBe("show-sim-7-away-analyst-es-ES");
    expect(pickShow(fx.shows, "analyst", "away", "fr-FR")!.lang).toBe("en-GB");
    expect(pickShow(fx.shows, "analyst", "away")!.lang).toBe("en-GB");
  });

  it("falls back to en-GB per moment when a moment is not yet in the language", () => {
    // Show overlays wait for a producer; approve them so the live selection sees them.
    const live = (id?: string) =>
      pickShow(fx.shows, "analyst", "away", id)!.segments.map((g) => ({ ...g.overlay, approval: { state: "approved" as const, by: "test", at: null } }));
    const [en, enGb] = [live("es-ES"), live()];
    const gone = en[0].match_tc;
    const kept = en.filter((o) => o.match_tc !== gone);
    const got = selectOverlays([...enGb, ...kept], "show", "analyst", "away", "es-ES");
    const at = (t: number) => got.find((o) => o.match_tc === t)!.lang;
    expect(at(gone)).toBe("en-GB");
    for (const o of kept) expect(at(o.match_tc)).toBe("es-ES");
  });
});

describe("tapping comma-decimal numbers", () => {
  const overlays = es.flatMap((s) => s.segments.map((g) => g.overlay));

  it("maps '14,4' to the 14.44 m claim, not '14,' to it", () => {
    const o = overlays.find((ov) => ov.claims.some((c) => c.text_slot === "gap_m" && c.tool_call.name !== "ghost"))!;
    const gap = o.claims.find((c) => c.text_slot === "gap_m")!;
    const spoken = Number(gap.value).toFixed(1).replace(".", ",");
    expect(o.script.text).toContain(spoken);
    expect(claimForWord(o, `${spoken}`)).toBe(gap);
    expect(claimForWord(o, "metros")).toBeUndefined();
  });

  it("puts every es-ES claim on a spoken word with evidence", () => {
    for (const o of overlays) {
      expect(claimWords(o).size, o.id).toBe(o.claims.length);
      for (const c of o.claims) expect(evidenceFor(fx.evidence, c), `${o.id} ${c.id}`).toBeDefined();
    }
  });
});
