# Making sim-7 read as football (stream B)

The demo match is `generate --seed 7 --half-minutes 5 --demo`. The research on other methods is in `b-realism-research.md`.

## What a viewer saw before
- **One-all, with goals that look like nothing.** The scripted home goal (beat at 150 s) arrived at 250 s, a 30 m shot. The away goal at 349 s was unscripted.
- **No goal moment.** The ball stayed in the net. The scorer jogged straight back while everyone walked to kick-off positions, and the ball teleported to the centre spot 6 s before the kick-off.
- **Keepers.** A keeper who saved a shot then dribbled the ball upfield, and keepers chased loose balls anywhere on the pitch.
- **No attacks.** About 0.4 shots a minute, no crosses and no runs into the box. Both teams clustered in midfield.
- **Scorebug.** The web scorebug is hard-coded to `HOME 0 – 0 AWAY` (`web/src/App.tsx:280`), so even real goals never showed up in the score.

## What changed (`sim/src/chalktalk_sim/director.py`)
- **The demo script is now three goals** (`DEMO_BEATS`):
  - a home goal from the 150 s beat, which goes to VAR (goal stands);
  - an away equaliser from the 390 s beat;
  - a home winner from the 510 s beat.
  - The final score is 2-1. When a match has scripted goals, unscripted shots on target are saved, so the script is the score. This held for seeds 7–12.
- **Goals land promptly.** While a team's goal beat is due:
  - it passes forward more and is tackled and intercepted less;
  - the other side wins the ball back faster;
  - shots come from central areas only (|y| < 20 m), so there are no goals from the touchline.
  - Seed 7 now scores at 185 s, 414 s and 540 s.
- **The goal sequence:**
  - the scorer wheels away to the corner flag and team-mates pile on (9 s);
  - the conceding team trudges back and its keeper fetches the ball;
  - everyone walks to kick-off positions while the ball is played back to the centre spot. It never jumps more than 1 m per frame;
  - kick-off waits until both teams are in position (at most 6 s extra).
  - From goal to kick-off takes 24–30 s, or 30 s with VAR.
- **Keepers:**
  - a keeper with the ball in hand stands still for 2.5 s and can't be tackled, then distributes it;
  - keepers only come for loose balls inside their own box.
- **Attacks:**
  - in the final third, forwards make runs into the box (near post, far post, penalty spot);
  - wide players in the final third cross to the team-mate in the box nearest goal;
  - players in the box are a little keener to shoot.
- **Half-time VAR.** VAR events that are still pending at the whistle are settled before `period_end`. Before this fix they leaked into the next goal.
- **Realism CLI.** `python -m chalktalk_sim realism` reads the committed IDSSE profile by default (the old `["metrics"]` key raised `KeyError`), and it reports `mean_ks`.

Tests are in `sim/tests/test_goal_sequence.py`:
- the script is the score;
- each goal follows its "goal" shot within 60 s of its beat;
- VAR comes before the restart;
- celebration pile-up, ball walk-back with no teleport, and kick-off timing;
- the keeper holds the ball after a save.

In `mcp/tests/test_summary_tools.py`, the catch-up windows moved because the fixture's goal now lands at 52 s, not about 75 s.

## Realism (mean KS against IDSSE, seeds 7 and 8, demo beats)
| halves | accel | ball speed | pass length | pressure | speed | team length | team width | **mean** |
|---|---|---|---|---|---|---|---|---|
| 5 min, before | 0.114 | 0.166 | 0.198 | 0.185 | 0.101 | 0.195 | 0.138 | **0.157** |
| 5 min, after | 0.114 | 0.204 | 0.183 | 0.168 | 0.083 | 0.174 | 0.157 | **0.155** |
| 45 min, before | 0.119 | 0.145 | 0.147 | 0.184 | 0.099 | 0.226 | 0.144 | **0.152** |
| 45 min, after | 0.121 | 0.139 | 0.141 | 0.181 | 0.097 | 0.226 | 0.150 | **0.151** |

The test gate is still mean KS < 0.3. Shots per 90 minutes are about 40, as before. Ball speed in the 5-minute demo is a little further from the reference because more of the match is goal sequences.

## What other streams need to do
- **Stream A (web):**
  1. **The scorebug.** Derive the score at time `t` from the last `goal` event at or before `t` (`attrs.score` = `{home, away}`); before the first goal it is 0-0. The final score is also in `manifest.meta.score`. No contract change is needed.
  2. **A goal banner** on each `goal` event. Show "GOAL", the scorer's name and the new score for about 5 s, during the celebration (players pile up for 9 s after the event). For the first goal, a "VAR check" chip from `var_check` until `var_decision`, then "Goal stands".
  3. **Regenerate** `web/public/fixtures/show-sim-7.json` and `queue-sim-7.json` with the commands in `a-demo-path.md`. The goal times moved from about 250 s to 185 s, 414 s and 540 s, so the chosen moments change.
- **Coordinator:** rebuild the live package with `python -m chalktalk_sim generate --seed 7 --half-minutes 5 --demo` and the crew cache for sim-7, then redeploy.
