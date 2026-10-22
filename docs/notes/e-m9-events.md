# M9: auto-eventing from video (stream E)

`python -m chalktalk_vision.m9` turns S5 pitch tracks into `event` contracts. Each event has `source: "video"`, a `confidence`, and `actors` as track ids (`T<id>`). It then scores them against the sim's events for the same window. The clip, detector and calibration are the same as in `e-s5-vision.md`: seed 7, 225–255 s, 14 sim events.

## How events are found (`vision/src/chalktalk_vision/events.py`)
- **Ball path:** ground positions with short gaps filled. A gap of up to 2 s is also filled when the ball reappears within 2 m, because a detector loses the ball at a player's feet.
- **Possession:**
  - The owner is the nearest home or away person within 1.3 m of the ball.
  - A run needs at least 3 frames; same-owner runs with short gaps are merged.
  - The release is the last frame the ball is still at the owner's feet, up to 5 frames past the run's end.
- **After each run**, the event is the first of these that applies:
  1. **Shot:** a 6-parameter ballistic fit (3D release point and velocity) from the ball's image-ray ground projections over 15 frames, solved as linear least squares with priors. An arc that reaches the goal line inside the frame (with 2 m slack) is a shot. Inside the posts and under the bar, followed by a restart, it is a goal.
  2. **Pass:** next owner is a team-mate within 3 s.
  3. **Clearance:** the ball leaves the own half at 16 m/s or more.
  4. **Incomplete pass, or tackle / interception:** the next owner is an opponent.
- **Other events:**
  - **Carry:** 3 m or more on the ball.
  - **Press:** an opponent within 2 m for at least 0.5 s.
  - **Ball out:** the ball teleports (a sim restart) after last being seen near a line.
  - **Goal kick:** the next touch after an out, on the goal area.
- **Attack direction** comes from the goalkeepers' mean x.
- **Ball gating** (`pick_balls` in `pitch_tracks.py`, new in this PR): COCO RF-DETR also fires weakly on the penalty and centre spots. A weak candidate is only taken if it is near the last ball position; re-acquiring the ball needs a score of 0.35 or more. Effect on S5 ball scores:
  - Precision 0.888 → **0.984**.
  - Recall 0.844 → 0.833.

## Results
- Match tolerance is ±1 s with the same event type.
- The actor check maps tracks to players by majority box IoU, for scoring only.
- "Visual" leaves out var_check, var_decision, substitution, period_end and card.

| tracks | precision | recall (all 14) | recall (13 visual) | timing MAE | actor accuracy |
|---|---|---|---|---|---|
| oracle boxes (truth) | 0.80 | **0.857** | **0.923** | 32 ms | 1.0 |
| RF-DETR-S + ByteTrack | 0.58 | **0.50** | **0.54** | 53 ms | 1.0 |

Per type, as video / sim / matched:

| type | oracle | detector |
|---|---|---|
| shot | 1/1/1 | 1/1/1 |
| goal | 1/1/1 | 1/1/1 |
| tackle | 2/1/1 | 2/1/1 |
| interception | 1/1/1 | 2/1/1 |
| clearance | 1/1/1 | 2/1/1 |
| carry | 2/2/2 | 1/2/1 |
| pass | 2/2/2 | 1/2/1 |
| press | 3/2/1 | 2/2/0 |
| ball_out | 1/1/1 | 0/1/0 |
| goal_kick | 1/1/1 | 0/1/0 |
| var_check | 0/1/0 | 0/1/0 (not visible) |

### Reading the numbers
- **The logic is sound.** On truth boxes, 12 of 13 visual events are found with the right actor, within 32 ms on average.
- **Detector misses are almost all ball-visibility misses:**
  - The ball rolls out over the goal line next to the advertising boards. The detector loses it there, so there is no teleport to see. That drops `ball_out`, and with it the next `goal_kick` and the carry before it.
  - The goal-kick pass is also lost: the ball sits at the goalkeeper's feet for 5 s and is detected only intermittently.
- **The headline moment survives on detector tracks:** the shot and the goal are both found, timed and attributed correctly.
- **Precision drops** from a few duplicate challenge events (an extra interception and clearance) around ID switches.
- **Every emitted event validates** against `contracts/schemas/event.schema.json` (checked in the tests).

### What would raise detector recall (not done)
1. A ball-specific detector. A small RF-DETR fine-tune on rendered frames is cheap, because the renderer gives exact labels.
2. Tracking in pitch space, to cut the ID switches behind the duplicate challenge events.
3. A sample bigger than one 30 s window (14 events) before trusting any per-type rate.

## Reproduce
After the S5 steps:
```bash
uv run python -m chalktalk_vision.m9 --clip scripts/render/out/demo \
    --pitch-tracks scripts/render/out/demo/pitch_tracks_detector.jsonl
uv run python -m chalktalk_vision.m9 --clip scripts/render/out/demo \
    --pitch-tracks scripts/render/out/demo/pitch_tracks_oracle.jsonl
```
