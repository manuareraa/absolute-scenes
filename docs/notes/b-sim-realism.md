# Stream B: sim realism (pressing, shots, xG)

Branch `stream/b-sim-realism`. Three fixes:
- Pressing reads near 50%, not 70–88%.
- Shots are about 24 per 90 for both teams, not 40–49.
- The xG weights are fitted on open data instead of set by hand.

sim-7 still ends 2–1.

## Before and after

### 90-minute matches, no script (seeds 1–3)

"Before" is `main` at 9008e4b. "After" is this branch. Both are measured with
`chalktalk_sim.stats.match_stats`, with pressing sampled every 10th frame.

| | Before | After | Real reference |
|---|---|---|---|
| Shots per 90, both teams (seeds 1/2/3) | 49 / 40 / 45 (mean 44.7) | 25 / 21 / 25 (mean 23.7) | 25.3 (PL 2022/23), 27.2 (PL 2023/24) [1] |
| xG per team per 90 (mean) | 3.14 | 1.04 | REFERENCE range 0.6–2.4 |
| xG per shot (pooled) | 0.141 | 0.088 | 0.119 goals per shot (PL) [1] |
| xG per side, seed 1 | 2.67 / 2.55 | 0.89 / 1.21 | |
| xG per side, seed 2 | 4.13 / 1.66 | 1.33 / 0.49 | |
| xG per side, seed 3 | 5.04 / 2.81 | 1.68 / 0.63 | |
| Score, seeds 1/2/3 | 2–3, 6–0, 3–5 | 2–0, 2–0, 2–0 | |
| PPDA range | 4.06–5.01 | 7.83–10.14 | 6–16; lowest PL team 8.62 (Liverpool 2021/22) [2] |
| Pressing intensity (mean) | 0.728 | 0.502 | 0.48–0.64 per team on two IDSSE matches [3] |
| Interceptions per 90 | about 230 | 64–90 | |
| Pass completion | about 0.80 | 0.79–0.81 | |

The scores are not scripted. Three 2–0s from three seeds is chance: the goals' shot xG
was 0.25 and 0.06, 0.54 and 0.05, and 0.46 and 0.04.

The parent session saw pressing at 81–88%. That figure came from a reading I did not
reproduce. The same core function over a whole 90 minutes gave 0.71–0.74 before this
change.

### sim-7, the shipped demo (5-minute halves, scripted)

| | Before | After |
|---|---|---|
| Final score | 2–1 | **2–1** |
| Shots (per 90) | 7 (63) | 5 (45) |
| xG home / away | 0.05 / 0.36 | 0.10 / 0.18 |
| Pressing home / away | 0.697 / 0.711 | 0.551 / 0.480 |
| PPDA home / away | 9.75 / 9.0 | 9.0 / none (no away defensive actions in the zone) |
| Saves | 3 | 1 |

Shots per 90 is still high in sim-7. Ten minutes is too short a sample, and the script
forces three goals and one save into it.

### sim-7 moments

| Moment | Before (ms) | After (ms) | Change |
|---|---|---|---|
| Away shot saved | 61 440 (A11, xG 0.093) | 67 040 (A09, xG 0.172; save 67 440) | Moved 5.6 s; new scripted "save" beat at 60 s |
| Away shot off target | 95 600 (A11, xG 0.139) | none | **Gone** |
| Home shot off target | none | 91 200 (H11, xG 0.043) | New |
| Home goal 1 | shot 184 120, goal 185 120 (H09, xG 0.033) | shot 175 400, goal 176 800 (**H11**, xG 0.017) | Moved 8.3 s earlier; scorer H09 → H11 |
| VAR check / decision | 188 120 / 199 120 | 179 800 / 190 800 | Moved with goal 1 |
| Away shot saved | 348 960 (A09, xG 0.042) | none | **Gone** |
| Away goal | shot 412 920, goal 413 760 (A09, xG 0.064) | shot 447 400, goal 448 840 (A09, xG 0.013) | Moved 35 s later; same scorer |
| Away shot saved | 518 040 (A11, xG 0.023) | none | **Gone** |
| Home goal 2 (winner) | shot 538 840, goal 539 840 (H07, xG 0.021) | shot 530 680, goal 531 600 (**H11**, xG 0.043) | Moved 8.2 s earlier; scorer H07 → H11 |

Same seed (7), same beats (goals at 3:00, 7:00 and 8:50; VAR on the first goal). A save
beat at 1:00 was added so the demo still has a keeper save at a realistic shot rate.

The sim runs on one random stream, so any change to behaviour reshuffles every later
moment. Keeping the exact old times was not possible.

**Downstream:** `web/public/fixtures/show-sim-7*` and `queue-sim-7.json` are keyed to the
old moment ids (`m184120`, `m185120`, …). When the coordinator regenerates the shipped
sim-7 package, those fixtures, and the overlays and audio, need regenerating too.

I regenerated the package locally with:

```bash
uv run python -m chalktalk_sim generate --seed 7 --half-minutes 5 --demo --out <scratch>/packages
```

It reports score 2–1. The package was not committed.

The scripted goals still come from low-xG shots (0.01–0.04). They are taken from the first
reasonable position once a beat is due. Raising their xG would mean holding the beat for
a better chance, which risks missing the beat window.

## What changed

### Pressing (core `analytics.press_probabilities`)

The definition follows Bekkers (2025) [3]:
- Time to intercept is a 0.7 s reaction time plus distance at 7 m/s.
- A logistic with σ = 0.45 is applied at a 1.5 s horizon.

The fix is the **active presser gate**, following Bekkers' figure 2: a defender counts only
if one of these holds.
- They run at 2 m/s or more and are closing on the carrier.
- They are within 1.5 m (contact).

Before, defenders who were standing or leaving still scored, so pressing read high.

Checked on real play (IDSSE, DFL), with the same function:

| Match | Home | Away | All |
|---|---|---|---|
| J03WMX | 0.607 | 0.589 | 0.599 |
| J03WN1 | 0.637 | 0.476 | 0.555 |

The old definition gave 0.685 and 0.682 on those matches. `stats.REFERENCE["pressing"]`
is (0.45, 0.70).

### Shots (sim `director` and `calibration`)

These calibration fields are new or changed:

| Field | Value | Effect |
|---|---|---|
| `shot_appetite` | 1.4 | Was a hard-coded 2.2 |
| `shot_xg_cap` | 0.08 | New. The chance to shoot is `min(xg, cap) * appetite + box boost`, so close chances don't crowd out long shots. |
| `shot_box_boost` | 0.04 | Was 0.12 |
| `shot_on_target` | 0.45 | Unscripted P(goal \| on target) = xG / 0.45 |
| `interception_min_speed_ms` | 8.0 | Slower balls won are a silent recovery, not an "interception" event. This took interceptions from about 230 per 90 to under 100. |
| `beat_shot_min_xn`, `beat_any_shot_s` | 33 m, 25 s | A due scripted goal is shot from the box or 33 m past halfway. After 25 s overdue, any shot in range. |

There is also a new beat kind: `save`.

### xG (core `analytics.xg`)

A logistic on distance (m) and the goal-mouth angle (rad):

`z = -1.430 - 0.0900 * distance + 1.414 * angle`

It was fitted on the Wyscout open event data [4]:
- England, Germany and Spain 2017/18.
- eventId 10 open-play shots: 23,328 shots, 2,545 goals.
- Mean xG 0.109 equals the goal rate. Log loss 0.298, Brier 0.0858.

Only the three coefficients are in the repo. No data is committed or shipped.

Benchmark against DFL's own xG on 40 IDSSE shots (8 of them headers):

| Model | Sum | Pearson | MAE | Footed shots sum |
|---|---|---|---|---|
| DFL | 4.21 | | | 3.78 |
| Old hand-set weights | 6.25 | 0.492 | 0.096 | 4.24 |
| Fitted | 5.13 | 0.491 | 0.080 | 3.53 |

The fit has no header term, so it over-rates headers. That explains most of the gap to DFL.

Fitted values for a central shot:

| Distance | xG |
|---|---|
| 6 m | 0.396 |
| 11 m (penalty spot) | 0.181 |
| 16.5 m | 0.091 |
| 22.5 m | 0.047 |

### Tests

- `sim/tests/test_realism_stats.py` pools seeds 1–3 with 15-minute halves. It holds these
  inside `stats.REFERENCE`:
  - shots per 90
  - xG per team and xG per shot
  - median PPDA
  - mean pressing
  - pass completion
- Core tests cover the active-presser gate and the new xG bounds.
- `mcp/tests/test_summary_tools.py`: the sim-11 fixture's goal now lands at 43 s, so the
  catch-up window moved from 45 s to 41 s.

## Request to the coordinator: docs/data-credits.md

The xG fit used CC BY 4.0 data. Please add this to `docs/data-credits.md`, which is a
coordinator path:

- Pappalardo, L., Cintia, P., Rossi, A., Massucco, E., Ferragina, P., Pedreschi, D. and
  Giannotti, F. (2019). *A public data set of spatio-temporal match events in soccer
  competitions.* Scientific Data 6, 236. https://doi.org/10.1038/s41597-019-0247-7.
  Dataset: figshare, events article 7770599 (https://figshare.com/articles/dataset/7770599).
  Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
- Changes: we fitted a three-coefficient logistic xG model on the open-play shots from the
  England, Germany and Spain 2017/18 event files. Only the coefficients are in
  `core/src/chalktalk_core/analytics.py`. No events, names or ids are committed, shipped
  or shown.

## Sources

1. The Analyst (Opta). Premier League shots per match: 25.3 in 2022/23 and 27.2 in
   2023/24. Shot conversion 11.88%.
2. Trainor, C. (2014). PPDA, StatsBomb. Liverpool's 8.62 PPDA in 2021/22 (Wyscout) was
   the lowest in the Premier League, reported by Coaches' Voice and premierleague.com.
3. Bekkers, J. (2025). *Pressing Intensity: An Intuitive Measure for Pressing in Soccer.*
   arXiv:2501.04712. IDSSE reference values were measured here on the Bassek et al. (2025)
   data; see `b-data-credits.md`.
4. Pappalardo et al. (2019), above.
