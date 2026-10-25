# Believable demo moments (2026-10-25)

The judge review asked for a VAR call that is genuinely close and for goals that come from real
chances. The sim (`a7678b0`) now scripts both.

| Moment | Now (seed 7, `--half-minutes 5 --demo`) |
|---|---|
| VAR check | Pass finds the striker 0–0.3 m behind the line; the call is onside by 0.04 m, goal stands (2:09) |
| Goals | Each scripted goal needs at least 0.15 xG unless the beat is long overdue: 0.27 xG (2:09), 0.19 xG (7:15), 0.38 xG (8:53) |

Score 2-1, 1-0 at half time. The ghost chapter moved to 8:53 (`ov-ghost-m533560-H11-*`).

## Rebuild
- Show, queue, voice and the two rehearsal ask feeds rebuilt from the new match (`d40b8d1`); the
  58 voice clips of the old match removed. 120 clips, 11.2 MB, every cue on its word (0 ms gap).
- Crew run: 54 overlays, 170 agent runs (director 1, analyst 54, pundit 61, verifier 54), 0 agent
  fallbacks, about $0.056 in tokens. 3 of the 54 Pundit scripts failed the rules twice and used
  the rule-based writer (the old show had 8). The VAR and ghost chapters use fixed scripts by design.
- Claims verified 198 of 198; all 90 chapters passed the gate; evidence re-runs 14 of 14.

## Evaluation
Foundry evaluation `31df2799-e2b7-4550-86de-3ae8ca96c212`; scores in `evals/results/2026-10-25-foundry.json`. 64 items:
the 54 show overlays and 10 synthetic test items.

| evaluator | score |
|---|---|
| claim groundedness (code) | 1.0, 64/64 |
| numeric tolerance (code) | 1.0, max error 0 |
| cue timing (code) | p95 0 ms, 64/64 |
| Foundry `GroundednessEvaluator` (LLM judge) | mean 4.98 (63 fives, 1 four) |

Judge cost about $0.048. No Azure resources created.

## Deployed
- Worker version `10bfbb4c` (web build with the new show).
- `chalktalk-ask` on `ghcr.io/manuareraa/chalktalk-ask:sha-d40b8d1` (new sim, faster first
  feedback, distances said as distances, zero-padded clock). `minReplicas` 0.
