import type { Strings } from "../i18n";

/** Broadcast score bug: team names in their kit colours, the score, and the match clock. */
export function ScoreBug({ s, score, clock }: { s: Strings; score: { home: number; away: number }; clock: string }) {
  return (
    <div className="scorebug" role="status" aria-label={`${s.teams.home} ${score.home}, ${s.teams.away} ${score.away}, ${clock}`}>
      <span className="team home">
        {s.teams.home}
      </span>
      <b>
        {score.home} – {score.away}
      </b>
      <span className="team away">
        {s.teams.away}
      </span>
      <span className="tc">{clock}</span>
    </div>
  );
}
