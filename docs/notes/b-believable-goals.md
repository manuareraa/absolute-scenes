# Believable goals and shots (stream B)

Branch `stream/b-believable-goals`. This changes `sim/` only. The shipped shows, packages and fixtures were **not** regenerated: the coordinator must rebuild the seed-7 demo package and any fixtures made from the sim, because the seed-7 moments below have moved.

## What looked silly (audit of origin/main)

The audit script lives in the session scratch dir, not the repo. It checks every shot for the following:
- **Keeper position:** he should stand within 2 m of the line from the ball to the goal centre.
- **Keeper reaction:** a keeper who is still while the ball passes 0.6 to 2.5 m from him.
- **Goals through the keeper:** a goal that passes within 1.2 m of his body.
- **Shots through defenders:** a low ball (under 1.9 m) that passes within 0.5 m of an outfield defender with no deflection.
- **Shot position:** a shot from more than 35 m out, from his own half, or from off the pitch.
- **Ball speed:** a shot slower than 8 m/s or faster than 36 m/s.

It also checks player speed (over 10 m/s), player acceleration (over 8 m/s²), and ball jumps (over 40 m/s).

Configs:
- **7d / 8d:** the demo (`--seed N --half-minutes 5 --demo`).
- **11c:** the test conftest match.
- **1, 2, 3:** unscripted 2×45.

| run | shots flagged before | after | player ticks over 10 m/s (max) before | after | accel over 8 before | after |
|---|---|---|---|---|---|---|
| 7d | 4 of 5 (keeper off line 4, a 35.1 m goal) | 1 of 4 | 3 (57 m/s) | 0 (8.5) | 15 | 0 |
| 8d | 2 of 3 | 1 of 4 | 3 (57) | 0 (8.6) | 17 | 2 |
| 11c | 1 of 5 | 0 of 1 | 1 (57) | 0 (8.7) | 14 | 0 |
| 1 | 10 of 25 (off line 9, through defender 2, through keeper 1) | 5 of 26 | 2 (57) | 0 (8.3) | 41 | 1 |
| 2 | 12 of 21 (off line 12, 38.8 m shot) | 1 of 23 | 2 (57) | 0 (8.5) | 63 | 0 |
| 3 | 12 of 25 (off line 11, through keeper 1, 35.6 m shot) | 2 of 27 | 2 (57) | 0 (9.6) | 45 | 2 |

The root causes were these:
- **Keeper off his line.** The keeper wandered and sat on a fixed spot, so at most shots he was 2 to 12 m off the line from the ball to the goal.
- **Goal aim ignored players.** Goal shots were aimed at a random spot in the goal, without checking where the keeper or the defenders were.
- **Long shots when a beat was due.** A scripted beat that was overdue allowed shots from anywhere.
- **Kick-off teleport.** The kick-off moved the taker onto the spot, which shows as 57 m/s.
- **Ball snaps.** A controlled ball snapped to the player's feet; this caused about 200 ball jumps per match.
- **Stop at the edge.** The hard position limit 3 m off the pitch stopped players dead, which caused the acceleration spikes.

## What changed

The new calibration fields are in `calibration.py`, under "Believable shots".

- **Shot range.** Shots are taken only within `max_shot_dist_m` = 32 m and with a goal angle of at least `min_shot_angle_rad` = 0.12. This also applies to overdue beats. `beat_any_shot_s` changes from 25 to 15 s, so beats still land on time.
- **Keeper position.** The keeper stands on the line from his goal centre to the ball. His depth is `1 + 0.1·d` m, clipped to 1 to 9.5 m. When the ball is wide or behind the goal line, he hugs the near post. He no longer wanders.
  - During a shot he moves at the deceleration cap toward the line of the ball.
- **Goal aim.** A goal is aimed (`aim_goal`) only where the ball passes the keeper by at least `keeper_reach_m` = 1.4 m after his best dive. Every outfield defender in the lane must also be clear of the ball by at least 1.0 m (forced beats) or 0.5 m (other shots).
  - If there is no clear aim, a forced beat waits for a better chance. An ordinary shot becomes a save instead.
  - A save is aimed so that the ball meets the keeper.
- **Flight checks, every tick.**
  - A low ball that passes within `block_radius_m` = 0.5 m of a defender is blocked. The shot event gets `outcome: "blocked"` and `blocked_by`, and the ball deflects off him.
  - A goal that comes within 1.0 m of the keeper becomes a save.
  - In both cases the beat stays due, so a scripted goal can still come later.
- **Kick-off.** There is no teleport: the taker walks to the ball, and the kick-off waits until he is within 1.2 m of the centre.
- **Ball control.** A controlled ball is gathered toward the feet at the player's speed + 7.5 m/s, instead of snapping there.
- **Edge braking.** Near the edge of the frame area, players brake in time: their outward speed is limited to √(2·0.8·decel·room). This replaces the hard stop and keeps positions inside the frame contract (|x| ≤ 60, |y| ≤ 40).

**Known limit:** `test_player_kinematics_within_limits` caps the change in speed at 3.5 m/s², so a keeper can only dive about 0.2 to 1.4 m during a shot. The remaining `keeper_static` flags are goals where he could move only about 0.1 to 0.25 m in time. The goal still passes at least 1.6 m clear of him.

## New tests

`sim/tests/test_believable_shots.py` runs on the seed-7 demo and on seed 1 with 15-minute halves. It checks five things:
- Every shot is from within 32.5 m.
- At every shot, the keeper is within 2 m of the line from the ball to the goal.
- No player moves faster than 10 m/s.
- No goal's ball passes within 0.5 m of an outfield defender (ball under 1.9 m) or within 1.0 m of the keeper (ball under 2.4 m).
- A blocked shot names its blocker.

On origin/main, 4 of these 10 checks fail. All existing tests pass, including the realism stats and the KS test.

## Seed-7 demo moments (`--seed 7 --half-minutes 5 --demo`)

The final score is still 2–1 (home, away, home).

| before (main) | after |
|---|---|
| 1:07.0 away A09 saved, xG 0.172 | 0:25.9 home H07 saved, xG 0.038 |
| 1:31.2 home H11 off target, xG 0.043 | — |
| 2:55.4 home H11 **goal**, xG 0.017 (goal at 2:56.8) | 3:00.8 home H09 **goal**, xG 0.041 (goal at 3:01.5) |
| 7:27.4 away A09 **goal**, xG 0.013, from 35.1 m (goal at 7:28.8) | 6:56.3 away A11 **goal**, xG 0.043, from 23.0 m (goal at 6:57.2) |
| 8:50.7 home H11 **goal**, xG 0.043 (goal at 8:51.6) | 8:44.4 home H11 **goal**, xG 0.061 (goal at 8:45.0) |

The VAR check still follows the first goal. Any `moments` or overlay timings tied to the old goal times (2:56.8, 7:28.8, 8:51.6) must be rebuilt.

## Other seeds

The single RNG stream reshuffles everything after the first changed decision, so the unscripted results change:
- seed 1: 2–0 → 0–2
- seed 2: 2–0 → 0–0
- seed 3: 2–0 → 0–1

There are about 0 to 1 blocked shots per 90 minutes.

Scripted-goal lag (demo beats, seeds 1 to 12):
- **main:** mean 34.8 s, 5 goals over 60 s.
- **branch:** mean 33.5 s, 3 goals over 60 s. Seed 2 misses its third goal; seed 3's second goal comes 134 s late and seed 11's 83 s late. Seed 7 lags are 32, 27 and 15 s.
