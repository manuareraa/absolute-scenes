# Be the tactician (Oct 27)

The viewer pauses a moment, drags up to 3 players of one team (each at most 10 m), and taps "Test my idea". The crew skips the Tactician: the viewer's moves go straight to the Critic, which re-runs the frame with `what_if` and keeps the idea only if the measured numbers improve and none gets worse. The verdict is spoken in the viewer's language, with the before and after values and the moved players drawn as ghosts.

- Worker: `checkMoves` in `workers/edge/src/ask.ts` (1 to 3 moves, one team, ids `H1`..`A11`, inside the pitch).
- Crew: `_mine` and `_offsets` in `crew/src/chalktalk_crew/ask/crew.py`. A drag splits into `back_m` and `infield_m`, the axes `what_if` already takes, capped at 10 m. The Analyst and Pundit get a neutral "what happened in this moment?", so only the Critic speaks on the idea.
- Web: drag mode in `PitchView` (`reach` clamps to the 10 m ring and the pitch), chip under Ask the pundit, card under the pitch.

## Live checks (crew `sha-4442faa`, Worker `92ed2bf0`)
- EN, moment 1 (02:08), away #5 and #4 pushed up: rejected. Pitch control 0.71 → 0.73, line gap 11.3 m → 13 m. Gate passed.
- ES, moment 1 (02:08), side away, away #10, #6 and #9 dropped back 8–9 m: kept. Line gap 11.3 m → 9.7 m, pitch control 0.71 → 0.74. Gate passed, trace `aec51c9f`.

The ES run is the scripted "kept" moment for the video.

# You vs the Tactician (Oct 27)

After "Test my idea", a card under the pitch shows the viewer's result and a "Can the Tactician beat you?" button. It asks "What should <team> have done?" for the team the viewer moved, on the same moment, and the Tactician's proposal goes through the same `what_if` re-run and Critic. The card then names the winner by the Critic's own rule: kept beats dropped, then the higher `net` (metrics better minus metrics worse, from the moved team's view). Equal is a draw.

- Contract: `Counterfactual.net` (integer, optional), sent by both what_if emit sites in the crew.
- Web: `duelWinner` in `web/src/duel.ts` (tested in `web/test/duel.test.ts`), `Duel` in `web/src/studio/Studio.tsx`, state in `App.tsx`. A side's result is read once its stream has `finished`.

## Live checks (crew `sha-3262a68`, Worker `f858eecb`)
- ES, moment 1 (02:08), side away, away #10, #6 and #9 back about 8 m: viewer kept, +2 net (pitch control 0.71 → 0.74, line gap 11.3 m → 9.7 m). Tactician dropped, −1 net (pitch control 0.71 → 0.70). Card: "Le ganas al Táctico".
- EN, same moment, away #5 and #4 pushed up: viewer dropped, 0 net (pitch control 0.71 → 0.65, line gap 11.3 m → 9.2 m). Tactician dropped, −1 net. Card: "You beat the Tactician".

The Tactician's proposal differs from run to run, so the winner can change.
