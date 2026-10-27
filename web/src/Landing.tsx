// The front page a first-time visitor (or judge) lands on: what Absolute Scenes is, what to look for,
// and a "Show me" link per feature that opens the show at the chapter or panel that has it.
import { Logo } from "./components/Logo";
import type { Strings } from "./i18n";

/** Where a "Show me" link opens: picks for the header, plus a chapter or panel on the show. */
export type Jump = {
  surface: "show" | "broadcast";
  lens?: "casual" | "analyst" | "newcomer";
  side?: "home" | "away" | "neutral";
  lang?: string;
  chapter?: "first" | "ghost" | "var";
  open?: "evidence" | "summary";
  /** Points at the ask bar: its input, or the "What should they have done?" chip. */
  hint?: "ask" | "whatif";
};

export const START_SHOW: Jump = { surface: "show", lens: "analyst", side: "away", chapter: "first" };
export const START_LIVE: Jump = { surface: "broadcast" };

const JUMPS: Record<string, Jump> = {
  strokes: START_SHOW,
  ask: { ...START_SHOW, hint: "ask" },
  whatif: { ...START_SHOW, hint: "whatif" },
  ghost: { surface: "show", lens: "analyst", side: "away", chapter: "ghost" },
  var: { surface: "show", lens: "analyst", side: "away", chapter: "var" },
  evidence: { surface: "show", lens: "analyst", side: "away", chapter: "first", open: "evidence" },
  audiences: { surface: "show", lens: "newcomer", side: "home", lang: "es-ES", chapter: "first" },
  summary: { surface: "show", lens: "analyst", side: "away", open: "summary" },
  live: START_LIVE,
};

export function Landing({ s, lang, onLang, onGo }: { s: Strings; lang: string; onLang(lang: string): void; onGo(j: Jump): void }) {
  const l = s.landing;
  return (
    <main className="landing" lang={lang}>
      <header className="landing-bar">
        <Logo size={30} />
        <div className="seg" role="group" aria-label={s.groups.lang}>
          {["en-GB", "es-ES"].map((code) => (
            <button key={code} className={lang === code ? "on" : ""} aria-pressed={lang === code} onClick={() => onLang(code)}>
              {code === "es-ES" ? "ES" : "EN"}
            </button>
          ))}
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="kicker">{l.kicker}</p>
          <h1>{l.title}</h1>
          <p className="lede">{l.lede}</p>
          <div className="ctas">
            <button className="cta primary" onClick={() => onGo(START_SHOW)} autoFocus>
              <b>{s.watchShow}</b>
              <small>{s.watchShowHint}</small>
            </button>
            <button className="cta" onClick={() => onGo(START_LIVE)}>
              <b>{s.watchLive}</b>
              <small>{s.watchLiveHint}</small>
            </button>
          </div>
          <p className="honest">{l.honest}</p>
        </div>
        <HeroBoard />
      </section>

      <section className="features" aria-labelledby="features-title">
        <h2 id="features-title">{l.featuresTitle}</h2>
        <ol>
          {l.features.map((f, i) => (
            <li key={f.key}>
              <span className="idx">{String(i + 1).padStart(2, "0")}</span>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
              <button className="show-me" onClick={() => onGo(JUMPS[f.key])}>
                {l.showMe} →
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="measured" aria-labelledby="measured-title">
        <h2 id="measured-title">{l.measuredTitle}</h2>
        <ul>
          {l.measured.map((m) => (
            <li key={m.value}>
              <b>{m.value}</b>
              <span>{m.label}</span>
            </li>
          ))}
        </ul>
        <p className="measured-note">{l.measuredNote}</p>
      </section>

      <section className="built" aria-labelledby="built-title">
        <h2 id="built-title">{l.builtTitle}</h2>
        <ol>
          {l.built.map((b) => (
            <li key={b.name}>
              <b>{b.name}</b>
              <p>{b.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <footer className="landing-foot">
        <Logo size={20} />
        <span>{l.footer}</span>
      </footer>
    </main>
  );
}

/** A still of the idea: a chalk run and ring on a broadcast pitch, cued by the highlighted word. */
function HeroBoard() {
  return (
    <figure className="hero-board" aria-hidden="true">
      <svg viewBox="0 0 120 78">
        <defs>
          <radialGradient id="hb-vignette" cx="50%" cy="50%" r="70%">
            <stop offset="60%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.45" />
          </radialGradient>
          <marker id="hb-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M0 0L10 5L0 10z" fill="var(--signal)" />
          </marker>
        </defs>
        <rect width="120" height="78" rx="3" className="grass" />
        {Array.from({ length: 6 }, (_, i) => (
          <rect key={i} x={i * 20} width="10" height="78" className="stripe" />
        ))}
        <g className="markings" fill="none">
          <rect x="4" y="4" width="112" height="70" />
          <line x1="60" y1="4" x2="60" y2="74" />
          <circle cx="60" cy="39" r="9" />
          <rect x="98" y="21" width="18" height="36" />
          <rect x="110" y="30" width="6" height="18" />
        </g>
        <rect width="120" height="78" rx="3" fill="url(#hb-vignette)" />
        <path d="M58 52 C70 50 80 44 92 34" className="hb-run" markerEnd="url(#hb-arrow)" />
        <circle cx="96" cy="31" r="5" className="hb-ring" />
        {[
          [58, 52, "home", 8],
          [70, 28, "home", 10],
          [46, 40, "home", 6],
          [86, 46, "away", 4],
          [90, 26, "away", 5],
          [84, 36, "away", 6],
          [104, 39, "away", 1],
        ].map(([x, y, team, n]) => (
          <g key={`${team}${n}`} className={`player ${team}`}>
            <circle cx={x} cy={y} r="2.4" />
            <text x={x} y={Number(y) + 0.9}>
              {n}
            </text>
          </g>
        ))}
      </svg>
      <figcaption>
        “Watch the <mark>run</mark> in behind into the <mark className="b">space</mark>…”
      </figcaption>
    </figure>
  );
}
