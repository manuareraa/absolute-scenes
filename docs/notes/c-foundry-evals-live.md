# Stream C: M10 evaluations logged to Foundry (2026-10-23)

This run is logged in the Foundry project `chalktalk`, under Evaluations, as
`chalktalk-s4-evaluators` (id `e8e218b2-500a-4de8-91bc-a47dd08b4dcb`). The scores are in
`evals/results/2026-10-23-foundry.json`.

## What was scored (11 items)
- **10 synthetic items** come from the fake crew: the test moments × 3 lenses × 3 sides. They
  use no tokens.
- **1 live item** comes from the M4 smoke run (`c-foundry-agents.md`): Foundry agents on
  gpt-4.1-mini, live Speech, and the overlay as cached. `--live-cache` re-runs its tool calls on
  the same seeded match, so the evaluators compare its claims with fresh tool outputs.

## Scores
| evaluator | score | pass rate |
|---|---|---|
| claim groundedness (code: spoken numbers ⊆ claims ⊆ tool outputs) | 1.0 | 11/11 |
| numeric tolerance (code) | 1.0, max error 0 | 11/11 |
| stroke-to-word cue timing (code: cue p95 ≤ 50 ms of a word start) | p95 0 ms, no negative starts | 11/11 |
| Foundry `GroundednessEvaluator` (LLM judge, 1 to 5) | mean 4.91 | 11/11 at ≥ 3 |

The judge gave 10 items 5 and one 4 (`ov-m2401200-casual-home-en-GB`: a fine reading, it was
being strict). It gave the live item 5.

**Gap found.** The live script says "a high 0.01 expected goals chance". The numbers are
grounded, so every evaluator passes it, and so does the LLM groundedness judge. The adjective is
wrong, and nothing checks qualitative words against values yet. A next step, not done here: a
small code evaluator that flags "high", "big" or "low" against per-unit bands (for example,
xG < 0.1 is never "high").

## Tokens and cost
| | tokens | USD |
|---|---|---|
| M4 live smoke (5 agent runs) | 2,085 in + 216 out | 0.0012 |
| first smoke attempt (failed at Speech after its agent runs) | about the same | ≤ 0.001 |
| LLM judge, 11 items (estimated; the SDK did not report usage) | about 15k in + 1.3k out | 0.0083 |
| logging to Foundry, code evaluators | 0 | 0 |
| **total** | | **about $0.011** |

No Azure resources were created. App Insights was not needed: the eval results are stored in
the project.

## Re-run
```bash
set -a; . ~/.config/chalktalk/azure.env; set +a
PYTHONPATH=evals/src uv run --with azure-ai-evaluation python -m chalktalk_evals.foundry \
  --out .chalktalk-evals --live-cache <cache dir of a run> --log-to-foundry --judge
```
