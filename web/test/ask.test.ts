import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { validate, type Overlay } from "@chalktalk/contracts";
import { askMode, AskUnavailable, fakeAsk, idleStudio, liveAsk, pickFeed, readNdjson, startStudio, studioReduce, suggestionsFor, type AskEvent, type AskRequest, type FeedEntry } from "../src/ask";
import { ControlRoom, ghostStartMs, MetricChip, WhatIf } from "../src/studio/Studio";
import { tr } from "../src/i18n";

const ASK_DIR = join(__dirname, "../public/fixtures/ask");
const feedText = (lang: string) => readFileSync(join(ASK_DIR, `sim-7-counterfactual-${lang}.ndjson`), "utf8");
const events = (lang = "en-GB"): AskEvent[] =>
  feedText(lang)
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));

const req: AskRequest = { question: "What should they have done?", suggestion: "counterfactual", match_id: "sim-7", match_tc: 175000, lang: "en-GB", lens: "analyst", side: "away" };

const streamOf = (chunks: string[]) =>
  new ReadableStream<Uint8Array>({
    start(c) {
      const enc = new TextEncoder();
      for (const x of chunks) c.enqueue(enc.encode(x));
      c.close();
    },
  });

async function collect<T>(it: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const x of it) out.push(x);
  return out;
}

/** Serves files from public/fixtures/ask, like the Worker's static assets. */
const fixtureFetch = (async (url: string) => {
  const name = String(url).replace("/fixtures/ask/", "");
  try {
    return new Response(readFileSync(join(ASK_DIR, name), "utf8"));
  } catch {
    return new Response("", { status: 404 });
  }
}) as unknown as typeof fetch;

describe("readNdjson", () => {
  it("joins lines torn across chunks and keeps an unterminated last line", async () => {
    const got = await collect(readNdjson(streamOf(['{"type":"st', 'ep","seq":0,"t_ms":0}\n\n{"type":"done",', '"seq":1,"t_ms":5}'])));
    expect(got.map((e) => e.type)).toEqual(["step", "done"]);
  });
});

describe("rehearsal feed", () => {
  it("tells the whole story in order: tools, a rejected claim and its rewrite, the counterfactual, one overlay", () => {
    for (const lang of ["en-GB", "es-ES"]) {
      const ev = events(lang);
      expect(ev.map((e) => e.seq)).toEqual(ev.map((_, i) => i));
      expect(ev.at(-1)!.type).toBe("done");
      expect(ev.filter((e) => e.type === "overlay")).toHaveLength(1);
      const verdicts = ev.filter((e) => e.type === "verdict").map((e) => e.verdict!);
      expect(verdicts.some((v) => !v.ok)).toBe(true);
      expect(verdicts.at(-1)!.ok).toBe(true);
      // Every metric on a chip carries the tool call it came from.
      const cf = ev.find((e) => e.type === "counterfactual")!.counterfactual!;
      expect(cf.metrics.every((m) => m.tool_call)).toBe(true);
      // The overlay's claims are the tool's, never the pundit's.
      const o = ev.find((e) => e.type === "overlay")!.overlay!;
      expect(o.claims.every((c) => c.tool_call)).toBe(true);
      expect(o.strokes.some((s) => s.shape === "ghost_path")).toBe(true);
    }
  });

  it("picks the feed by question, match and language, nearest moment first", () => {
    const feeds: FeedEntry[] = [
      { key: "counterfactual", match_id: "sim-7", match_tc: 175400, lang: "en-GB", file: "a" },
      { key: "counterfactual", match_id: "sim-7", match_tc: 175400, lang: "es-ES", file: "b" },
    ];
    expect(pickFeed(feeds, req)?.file).toBe("a");
    expect(pickFeed(feeds, { ...req, lang: "es-MX" })?.file).toBe("b");
    expect(pickFeed(feeds, { ...req, lang: "fr-FR" })?.file).toBe("a");
    expect(pickFeed(feeds, { ...req, suggestion: "press" })).toBeUndefined();
    expect(pickFeed(feeds, { ...req, match_id: "other" })).toBeUndefined();
  });

  it("replays the recorded events, and refuses honestly when it has no answer", async () => {
    const c = new AbortController();
    const got = await collect(fakeAsk(req, c.signal, { speed: 0, fetchFn: fixtureFetch }));
    expect(got).toEqual(events());
    const none = await collect(fakeAsk({ ...req, suggestion: undefined, question: "Who wins the league?" }, c.signal, { speed: 0, fetchFn: fixtureFetch }));
    expect(none.map((e) => e.type)).toEqual(["step", "refusal", "done"]);
  });
});

describe("live route", () => {
  const respond = (status: number, body = "") => (async () => new Response(body, { status })) as unknown as typeof fetch;

  it("reads a missing backend as unavailable, so the rehearsal feed can stand in", async () => {
    for (const status of [404, 501]) await expect(collect(liveAsk(req, new AbortController().signal, respond(status)))).rejects.toBeInstanceOf(AskUnavailable);
    const offline = (async () => {
      throw new TypeError("network");
    }) as unknown as typeof fetch;
    await expect(collect(liveAsk(req, new AbortController().signal, offline))).rejects.toBeInstanceOf(AskUnavailable);
  });

  it("turns a rate limit or the kill switch into a reason for the viewer", async () => {
    expect((await collect(liveAsk(req, new AbortController().signal, respond(429))))[0]).toMatchObject({ type: "error", text: "busy" });
    expect((await collect(liveAsk(req, new AbortController().signal, respond(503, '{"error":"off"}'))))[0]).toMatchObject({ type: "error", text: "off" });
  });

  it("streams the backend's events through", async () => {
    const ok = (async () => new Response(feedText("en-GB"), { status: 200 })) as unknown as typeof fetch;
    expect(await collect(liveAsk(req, new AbortController().signal, ok))).toEqual(events());
  });

  it("reads the mode from the URL", () => {
    expect(askMode(new URLSearchParams("ask=fake"))).toBe("rehearsal");
    expect(askMode(new URLSearchParams("ask=live"))).toBe("live");
    expect(askMode(new URLSearchParams(""))).toBe("auto");
  });
});

describe("studio state", () => {
  const run = (ev: AskEvent[]) => ev.reduce(studioReduce, startStudio(req.question, "rehearsal"));

  it("ends on the answer, with the rejected claim struck through once it is rewritten", () => {
    const st = run(events());
    expect(st.phase).toBe("answering");
    expect(st.overlay?.script.audio_url).toMatch(/^\/fixtures\/show-sim-7\/audio\//);
    const v = st.rows.filter((r) => r.kind === "verdict");
    expect(v.find((r) => r.kind === "verdict" && !r.verdict.ok)).toMatchObject({ superseded: true });
    expect(st.cached).toBe(true);
    expect(st.active).toBe("pundit");
  });

  it("keeps an accepted proposal over a later rejected one", () => {
    const cf = (accepted: boolean, proposal: string): AskEvent => ({ type: "counterfactual", seq: 0, t_ms: 0, agent: "tactician", counterfactual: { proposal, accepted, metrics: [] } });
    expect(run([cf(true, "a"), cf(false, "b")]).counterfactual?.proposal).toBe("a");
    expect(run([cf(false, "a"), cf(false, "b")]).counterfactual?.proposal).toBe("b");
  });

  it("shows a refusal and a stream that ends without an answer as such", () => {
    expect(run([{ type: "refusal", seq: 0, t_ms: 0, text: "rehearsal" }]).phase).toBe("refused");
    expect(run([{ type: "step", seq: 0, t_ms: 0, agent: "director", text: "x" }, { type: "done", seq: 1, t_ms: 1 }]).phase).toBe("error");
    expect(idleStudio.phase).toBe("idle");
  });

  it("always offers 'What should they have done?' first, then a question for the moment", () => {
    expect(suggestionsFor(null)).toEqual(["counterfactual", "space", "key_player"]);
    const o = { id: "ov-var-1", claims: [] } as unknown as Overlay;
    expect(suggestionsFor(o)[1]).toBe("offside");
  });
});

describe("studio components", () => {
  const s = tr("en-GB");
  const st = events().reduce(studioReduce, startStudio(req.question, "rehearsal"));
  const overlay = st.overlay!;

  it("draws the control room as a gallery: tally lights, tool runs, a struck claim", () => {
    const html = renderToStaticMarkup(createElement(ControlRoom, { st, s, lang: "en-GB", onBack() {} }));
    expect(html).toContain("cr-tally");
    expect(html).toContain("cr-source rehearsal");
    expect(html).toContain("<code>ghost</code>");
    expect(html).toMatch(/cr-row verdict rejected superseded/);
    expect(html).toContain(s.ask.onAir);
  });

  it("shows the before/after chips only once the ghosts are on the pitch", () => {
    const at = ghostStartMs(overlay)!;
    expect(at).toBeGreaterThan(0);
    const props = { cf: st.counterfactual!, overlay, s, lang: "en-GB" };
    expect(renderToStaticMarkup(createElement(WhatIf, { ...props, audioMs: at - 1 }))).toBe("");
    const html = renderToStaticMarkup(createElement(WhatIf, { ...props, audioMs: at + 1 }));
    expect(html).toContain("what-if rejected");
    expect(html).toContain("metric-chip");
  });

  it("signs points with a real minus and adds the unit", () => {
    const html = renderToStaticMarkup(createElement(MetricChip, { m: { name: "pc_pts", before: 0, after: -3 }, s, lang: "en-GB" }));
    expect(html).toContain("−3 pts");
  });
});

describe("rehearsal feeds", () => {
  it("speak the ask-event contract, line by line", () => {
    for (const lang of ["en-GB", "es-ES"]) for (const e of events(lang)) expect(validate("ask-event", e).errors).toEqual([]);
  });
});
