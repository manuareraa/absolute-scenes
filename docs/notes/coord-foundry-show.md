# Coordinator: the show made on Foundry Agent Service (2026-10-24)

The shipped show (`web/public/fixtures/show-sim-7.json`) was regenerated with the crew hosted on
Foundry Agent Service. Before this, the show's scripts came from direct `gpt-4.1-mini` calls; the
agents had only run in the one-moment smoke test (`c-foundry-agents.md`).

## Run
```bash
set -a; . ~/.config/chalktalk/azure.env; set +a
CHALKTALK_AGENTS=foundry CHALKTALK_AGENT_VERSION=pundit=3 CHALKTALK_MAX_TOKENS=300 \
  CHALKTALK_CREW_BACKEND=azure uv run --with azure-cognitiveservices-speech \
  python -m chalktalk_crew run --seed 7 --half-minutes 5 --max-moments 4 \
  --lenses casual,analyst,newcomer --sides home,away,neutral --lang en-GB,es-ES \
  --cache .chalktalk-cache-real-audio-v5 --budget-usd 0.15
uv run python web/scripts/show_fixture.py --cache .chalktalk-cache-real-audio-v5 --half-minutes 5 \
  --out $S/show-sim-7.json --queue $S/queue-sim-7.json
CHALKTALK_SPEECH_BACKEND=azure uv run --with azure-cognitiveservices-speech python -m chalktalk_crew \
  voice-show --fixture $S/show-sim-7.json --queue $S/queue-sim-7.json \
  --cache .chalktalk-cache-real-audio-v5 --half-minutes 5 --out web/public/fixtures
```
Agent versions: director 1, analyst 1, pundit 3, verifier 1 (`foundry_agents sync` found no
changes).

## Result
| | |
|---|---|
| agent runs | director 1, analyst 54, pundit 67, verifier 54; **0 fallbacks** |
| overlays | 54 generated, 0 rejected, 0 failed |
| tokens | 102,174 prompt + 11,468 completion |
| cost | **about $0.059** (plus a $0.0011 one-overlay smoke run first) |
| speech | 11,535 characters on F0 (free) |
| show | 18 shows, 90 chapters, 198 of 198 claims verified, 14 of 14 evidence replays match |

The Foundry Director kept three of the four candidate moments: the three goals (2:57, 7:29, 8:52).
The earlier in-process Director's top four (1:32, 2:57, 5:00, 5:21) missed two of the goals. So each
show now has three crew chapters plus the ghost chapter (moved to 2:55) and the VAR chapter.

## Evaluation
Logged in the Foundry project as evaluation `f5cbcbf2-8b57-4c14-8992-e563eb5c3694`; scores in
`evals/results/2026-10-24-foundry.json`. 64 items: the 54 show overlays (`--live-cache`, tools
re-run on the seeded match) and 10 synthetic test items.

| evaluator | score |
|---|---|
| claim groundedness (code) | 1.0, 64/64 |
| numeric tolerance (code) | 1.0, max error 0 |
| cue timing (code) | p95 0 ms, 64/64 |
| Foundry `GroundednessEvaluator` (LLM judge) | mean 4.94 (60 fives, 4 fours) |

Judge cost about $0.048. Total for this note's work: about $0.11. No Azure resources created.
