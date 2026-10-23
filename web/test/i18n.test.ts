import { describe, expect, it } from "vitest";
import { slotLabel } from "../src/evidence";
import { chapterTitles, momentHeadline, num, slotWords } from "../src/i18n";
import type { Moment } from "../src/summary";

const chapter = (title: string, match_tc: number, value: number) => ({ title, overlay: { match_tc, claims: [{ value, unit: "m" }] } });

describe("chapter titles", () => {
  it("use mm:ss, drop the crew's minute prefix, and tell repeated titles apart by their number", () => {
    const chapters = [chapter("2' · The gap between the lines", 79_240, 11.66), chapter("2' · The gap between the lines", 106_960, 14.4), chapter("5' · VAR check: offside?", 249_000, 10.6)];
    expect(chapterTitles(chapters, "en-GB")).toEqual(["01:19 · The gap between the lines: 11.7 m", "01:46 · The gap between the lines: 14.4 m", "04:09 · VAR check: offside?"]);
    expect(chapterTitles(chapters, "es-ES")[0]).toBe("01:19 · El hueco entre líneas: 11,7 m");
  });
});

describe("numbers and words", () => {
  it("formats numbers in the UI language and names slots in plain words", () => {
    expect(num(11.66, "es-ES")).toBe("11,7");
    expect(num("six", "en-GB")).toBe("six");
    expect(slotWords(slotLabel("pc_pts"), "en-GB")).toBe("pitch control");
    expect(slotWords(slotLabel("pc_pts"), "es-ES")).toBe("control del campo");
  });
});

describe("summary headlines", () => {
  const goal = { kind: "goal", team: "home", headline: "Goal, home: 1-0 (VAR: goal stands)", score_after: { home: 1, away: 0 }, var: { decision: "goal_stands" } } as unknown as Moment;
  const chance = { kind: "chance", team: "home", headline: "Chance, home: xG 0.01, saved", xg: 0.0123 } as unknown as Moment;

  it("rebuild goals and chances with team names, in the UI language", () => {
    expect(momentHeadline(goal, "en-GB")).toMatch(/^Goal, Reds: 1-0 \(VAR: goal stands\)$/i);
    expect(momentHeadline(chance, "en-GB")).toBe("Chance, Reds: xG 0.01, saved");
    expect(momentHeadline(chance, "es-ES")).toMatch(/^Ocasión, Rojos: xG 0,01, parada$/);
  });
});

describe("num", () => {
  it("keeps two decimals below 1, so a small xG never reads as 0", () => {
    expect(num(0.03, "en-GB")).toBe("0.03");
    expect(num(0.03, "es-ES")).toBe("0,03");
    expect(num(11.64, "en-GB")).toBe("11.6");
  });
});

describe("chapterTitles es-ES", () => {
  it("translates the chance chapters", () => {
    const ch = { title: "4' · The chance", overlay: { match_tc: 184000, claims: [] } };
    expect(chapterTitles([ch], "es-ES")[0]).toBe("03:04 · La ocasión");
  });
});
