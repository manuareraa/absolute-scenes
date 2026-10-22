// Builds the Worker's static assets folder (workers/edge/public, gitignored):
//   public/            <- web/dist (the web build)
//   public/matches/<id>/  <- match packages written by `python -m chalktalk_sim generate`
// Usage: node scripts/assemble.mjs [--packages <dir>]   (or CHALKTALK_PACKAGES=<dir>)
// Every subfolder of <dir> that holds a manifest.json is copied as one match.
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const edge = resolve(here, "..");
const out = join(edge, "public");
const web = resolve(edge, "../../web/dist");

const i = process.argv.indexOf("--packages");
const packages = i > 0 ? process.argv[i + 1] : process.env.CHALKTALK_PACKAGES;

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
if (existsSync(web)) {
  cpSync(web, out, { recursive: true });
} else {
  console.warn(`assemble: ${web} missing, run "npm run build" for the web app; writing a placeholder`);
  writeFileSync(join(out, "index.html"), "<!doctype html><title>ChalkTalk</title><p>web build missing</p>\n");
}

const ids = [];
if (packages) {
  for (const name of readdirSync(packages)) {
    const src = join(packages, name);
    if (!existsSync(join(src, "manifest.json"))) continue;
    cpSync(src, join(out, "matches", name), { recursive: true });
    ids.push(name);
  }
}
console.log(`assemble: ${out} (web ${existsSync(web) ? "ok" : "placeholder"}, matches: ${ids.join(", ") || "none"})`);
