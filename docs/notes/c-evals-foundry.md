# Stream C: Foundry evaluators (S4) and evaluations (M10)

Code: `evals/src/chalktalk_evals/foundry.py`. Tests (in CI, local only):
`crew/tests/test_foundry_evals.py`.

## Three custom evaluators
Each one is a plain callable in the shape that `azure.ai.evaluation.evaluate()` accepts. It
takes the columns `overlay` and `tool_outputs` and returns scores plus a `*_result` of pass or
fail.

| evaluator | passes when |
|---|---|
| `ClaimGroundednessEvaluator` | every spoken number is a claim value, in the overlay language's form (`0,42` in es-ES); every claim has a `tool_call`; that call's recorded output exists and has the claim's unit |
| `NumericToleranceEvaluator` | every claim value is within its tolerance of the recorded tool output |
| `CueTimingEvaluator` | every stroke has a cue, no stroke starts before the audio, and the cue sits within 50 ms (p95) of a spoken word start |

Each dataset row holds an overlay together with a fresh re-run of its tool calls. The
evaluators need no tool access, so they score the same way in CI, locally and in Foundry. The
negative tests check that each evaluator fails its own defect: a made-up number, a missing tool
output, a value off the tool's output, a cue between two words, an unbound stroke, and an
English decimal in a Spanish overlay.

## Dataset
`build_items` returns 10 rows across the test moments, the three lenses and the three sides.
`--lang` builds the rows in another language.

## Manual Foundry run (not in CI)
```bash
set -a; . ~/.config/chalktalk/azure.env; set +a
PYTHONPATH=evals/src uv run --with azure-ai-evaluation \
  python -m chalktalk_evals.foundry --out .chalktalk-evals [--log-to-foundry] [--judge]
```
- Without flags, it runs `evaluate()` locally. No Azure calls are made and it costs $0.
- `--log-to-foundry` uploads the run to the project's Evaluations page
  (`AZURE_AI_PROJECT_ENDPOINT`). It uses no tokens but needs the **Azure AI User** role, the
  same blocker as M4.
- `--judge` adds the built-in LLM `GroundednessEvaluator` on `gpt-4.1-mini`. It costs about
  $0.008 for 10 items, and the run prints that estimate.
- `azure-ai-evaluation` (about 58 packages) is pulled only for this run, with `uv run --with`.
  It is not in `uv.lock`.

## Result (2026-10-22, local `evaluate()`, $0)
On 10 items, all three evaluators passed every item: groundedness 1.0, tolerance 1.0 (max error
0), cue timing 1.0 (cue-to-word p95 0 ms, no negative starts).
