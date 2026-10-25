# Live ask eval (2026-10-25)

84 questions sent to the deployed `chalktalk-ask` Container App (Foundry agents on gpt-4.1-mini, Azure Speech, Prompt Shields): 78 football questions and 6 attacks. The football questions use 13 moments of the demo match (the 4 chapter times plus 10 evenly spaced times), each with a rotating question, view (analyst/away, casual/home, newcomer/neutral) and language (en-GB, es-ES). Then a Foundry evaluation judged every answer for groundedness and relevance.

Results: `evals/results/2026-10-25-ask-live.json`. Code: `evals/src/chalktalk_evals/ask_live.py`.

| What | Result |
|---|---|
| Football questions answered with a drawn overlay | 78 of 78; all passed the gate; 0 errors |
| Verifier, first-round claims | rejected 10 of 147; 0 still wrong after the rewrite |
| "What should they have done?" | Critic accepted 5 of 32 Tactician proposals (the rest did not improve the measured numbers) |
| Overlay ready | median 11.9 s, p90 16.2 s |
| LLM judge (Foundry), 78 answers | groundedness 4.28 / 5 (86% pass), relevance 4.10 / 5 (97% pass) |
| Attack questions | 6 of 6 ended safely: 2 refused by Prompt Shields, 3 declined by the Pundit, 1 ignored the instruction and answered about the moment |
| Cost | 198 model calls, $0.145 in tokens (about $0.0017 per answer); judge extra |

## What the low scores show
13 judge scores were below 3. They fall into two groups:
- The Pundit calls a pitch-control share "pressure" (for example, it says "pressure on the ball is 75%" when the 75% is the away team's pitch control). Every number is right, but the label is wrong. The Verifier checks numbers, not labels.
- With an empty `events` result, the Pundit says there is "no data" even when other tools returned numbers.

Both are fixes to the Pundit prompt, not to the tools. Not done yet.

## Caveat
This run used the demo match as shipped before the believable-moments sim change (same day). The numbers describe the crew, not one fixed match; re-run `ask_live` against the rebuilt show before quoting it as that match's result.
