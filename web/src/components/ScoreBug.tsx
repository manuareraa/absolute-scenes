import type { Strings } from "../i18n";

/** Broadcast score bug: three-letter team codes in their kit colours, the score, and the match clock. */
export function ScoreBug({ s, score, clock }: { s: Strings; score: { home: number; away: number }; clock: string }) {
  return (
    <div className="scorebug" role="status" aria-label={`${s.teams.home} ${score.home}, ${s.teams.away} ${score.away}, ${clock}`}>
      <span className="team home" title={s.teams.home}>
        {s.teamCodes.home}
      </span>
      <b>
        {score.home} – {score.away}
      </b>
      <span className="team away" title={s.teams.away}>
        {s.teamCodes.away}
      </span>
      <span className="tc">{clock}</span>
    </div>
  );
}
