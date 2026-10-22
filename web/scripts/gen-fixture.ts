// Writes the synthetic M1 fixture to public/fixtures/. Run: npm run gen:fixture --workspace web
import { writeFileSync } from "node:fs";
import { makeFixture } from "../src/fixture/synthetic.ts";

const fixture = makeFixture();
const out = new URL("../public/fixtures/demo-001.json", import.meta.url);
writeFileSync(out, JSON.stringify(fixture));
console.log(`wrote ${fixture.frames.length} frames, ${fixture.overlays.length} overlays to ${out.pathname}`);
