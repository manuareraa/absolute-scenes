import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SCHEMA_NAMES, strokeStartMs, validate, type ContractName, type Overlay } from "../src/index";

const examples = join(__dirname, "../../examples");
const load = (p: string) => JSON.parse(readFileSync(p, "utf8"));

describe("contracts", () => {
  it.each(SCHEMA_NAMES)("valid %s example passes", (name) => {
    const res = validate(name, load(join(examples, "valid", `${name}.json`)));
    expect(res.errors).toEqual([]);
    expect(res.ok).toBe(true);
  });

  const invalid = readdirSync(join(examples, "invalid")).filter((f) => f.endsWith(".json"));
  it.each(invalid)("invalid example %s is rejected", (file) => {
    const name = file.split(".")[0] as ContractName;
    expect(validate(name, load(join(examples, "invalid", file))).ok).toBe(false);
  });

  it("applies the stroke timing rule", () => {
    const ov = load(join(examples, "valid", "overlay.json")) as Overlay;
    expect(strokeStartMs(ov.script.cues, ov.strokes[0])).toBe(620 - 150);
    expect(strokeStartMs(ov.script.cues, ov.strokes[1])).toBe(1410 - 150);
    expect(() => strokeStartMs(ov.script.cues, { cue_id: "missing" })).toThrow();
  });
});
