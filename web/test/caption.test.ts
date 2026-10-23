import { describe, expect, it } from "vitest";
import { captionTokens } from "../src/playback";

describe("caption punctuation", () => {
  const w = (t: string) => t.split(" ").map((text) => ({ text }));
  it("puts the script's punctuation back on the spoken words", () => {
    expect(captionTokens("They created a shot worth 0.03 expected goals . Notice the gap, a clear risk.", w("They created a shot worth 0.03 expected goals Notice the gap a clear risk"))).toEqual(
      w("They created a shot worth 0.03 expected goals. Notice the gap, a clear risk.").map((x) => x.text),
    );
    expect(captionTokens("¿Qué pasó? «Nada».", w("Qué pasó Nada"))).toEqual(["¿Qué", "pasó?", "«Nada»."]);
    expect(captionTokens("a 11.6-metre gap", w("a 11.6 metre gap"))).toEqual(["a", "11.6-", "metre", "gap"]);
    expect(captionTokens("other words", w("not found"))).toEqual(["not", "found"]);
  });
});
