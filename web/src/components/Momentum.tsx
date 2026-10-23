import type { Momentum as Series } from "../scoreboard";
import type { Strings } from "../i18n";

const H = 12; // half-height of the strip in SVG units; home bars rise, away bars fall

/**
 * Momentum strip under the score bug: one bar per minute of match time, each side's shot xG (or
 * shot count) in that minute. Home above the line, away below; the yellow line is now.
 */
export function Momentum({ m, nowT, s, lang }: { m: Series; nowT: number; s: Strings; lang: string }) {
  const n = m.bins.length;
  const w = 100 / n;
  const fmt = (v: number) => (m.metric === "xg" ? v.toLocaleString(lang, { maximumFractionDigits: 2 }) : String(v));
  const total = (team: "home" | "away") => m.bins.reduce((a, b) => a + b[team], 0);
  const label = m.metric === "xg" ? s.momentum.xg : s.momentum.shots;
  const x = Math.min(100, Math.max(0, (nowT / m.endT) * 100));
  return (
    <figure className="momentum" title={s.momentum.hint(m.metric)} aria-label={`${label}: ${s.teams.home} ${fmt(total("home"))}, ${s.teams.away} ${fmt(total("away"))}`}>
      <figcaption>{label}</figcaption>
      <svg viewBox={`0 0 100 ${2 * H}`} preserveAspectRatio="none" aria-hidden="true">
        <line className="mid" x1={0} y1={H} x2={100} y2={H} />
        {m.bins.map((b, i) => (
          <g key={b.t}>
            {b.home > 0 && <rect className="home" x={i * w + w * 0.12} width={w * 0.76} y={H - (b.home / m.peak) * H} height={(b.home / m.peak) * H} />}
            {b.away > 0 && <rect className="away" x={i * w + w * 0.12} width={w * 0.76} y={H} height={(b.away / m.peak) * H} />}
          </g>
        ))}
        <line className="now" x1={x} y1={0} x2={x} y2={2 * H} />
      </svg>
    </figure>
  );
}
