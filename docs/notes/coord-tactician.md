# Be the tactician (Oct 27)

The viewer pauses a moment, drags up to 3 players of one team (each at most 10 m), and taps "Test my idea". The crew skips the Tactician: the viewer's moves go straight to the Critic, which re-runs the frame with `what_if` and keeps the idea only if the measured numbers improve and none gets worse. The verdict is spoken in the viewer's language, with the before and after values and the moved players drawn as ghosts.

- Worker: `checkMoves` in `workers/edge/src/ask.ts` (1 to 3 moves, one team, ids `H1`..`A11`, inside the pitch).
- Crew: `_mine` and `_offsets` in `crew/src/chalktalk_crew/ask/crew.py`. A drag splits into `back_m` and `infield_m`, the axes `what_if` already takes, capped at 10 m. The Analyst and Pundit get a neutral "what happened in this moment?", so only the Critic speaks on the idea.
- Web: drag mode in `PitchView` (`reach` clamps to the 10 m ring and the pitch), chip under Ask the pundit, card under the pitch.

## Live checks (crew `sha-4442faa`, Worker `92ed2bf0`)
- EN, moment 1 (02:08), away #5 and #4 pushed up: rejected. Pitch control 0.71 → 0.73, line gap 11.3 m → 13 m. Gate passed.
- ES, moment 1 (02:08), side away, away #10, #6 and #9 dropped back 8–9 m: kept. Line gap 11.3 m → 9.7 m, pitch control 0.71 → 0.74. Gate passed, trace `aec51c9f`.

The ES run is the scripted "kept" moment for the video.
