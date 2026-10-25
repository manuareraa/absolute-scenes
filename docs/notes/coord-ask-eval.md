# Live ask eval (2026-10-25)

84 questions sent to the live "Ask the pundit" crew (Foundry agents on gpt-4.1-mini, Azure Speech, Prompt Shields): 78 football questions and 6 attacks. The football questions use 13 moments of the demo match (the chapter times plus 10 evenly spaced times), each with a rotating question, view (analyst/away, casual/home, newcomer/neutral) and language (en-GB, es-ES). Then a Foundry evaluation judged every answer for groundedness and relevance.

Results: `evals/results/2026-10-25-ask-live.json`. Code: `evals/src/chalktalk_evals/ask_live.py`.

| What | Result |
|---|---|
| Football questions answered with a drawn overlay | 77 of 78; all 77 passed the gate; 1 error (deadline, see below) |
| Verifier, first-round claims | rejected 8 of 156; every answer that went on air passed the gate |
| "What should they have done?" | Critic accepted 6 of 34 Tactician proposals (the rest did not improve the measured numbers) |
| Overlay ready | median 12.5 s, p90 18.3 s |
| LLM judge (Foundry), 77 answers | groundedness 4.62 / 5 (95% pass), relevance 4.23 / 5 (100% pass) |
| Attack questions | 6 of 6 ended safely: 2 refused by Prompt Shields, 3 declined by the Pundit, 1 ignored the instruction and answered about the moment |
| Cost | 201 model calls, $0.148 in tokens (about $0.002 per answer); judge extra |

## What changed since the first run
The first run (same day, the demo match before the believable-moments rebuild; `evals/results/2026-10-25-ask-live-before-fix.json`) scored groundedness 4.28 / 5 (86% pass) and relevance 4.10 / 5 (97% pass). Its low scores had two causes, both fixed in commit `bb449cf` (Pundit agent version 4):
- **Wrong labels.** The Pundit called a pitch-control share "pressure". Each result now carries a label in the viewer's language that names the team ("the away team's share of pitch control", "el control del espacio del equipo visitante"), and the prompt says to name each number only with its own label.
- **"No data" answers.** When the Analyst ran only `events` and a ball nobody held, the general tools were skipped, so the Pundit had nothing to quote. Those calls no longer count as measured, so the general tools run. The Pundit also gets the events found and what could not be measured ("nobody had the ball"), and the prompt forbids saying there is no data.
- **Spanish answers** now use Spanish terms; the labels and the prompt both ask for them. A scan of all 77 answers found no "no data" phrasing and no English football terms in the Spanish answers.

The two runs use different versions of the match, so the change in scores is the crew and the match together, not the fix alone.

## What is left
- 4 judge scores were below 3, all groundedness. Two round a number (2.98 m said as 3.0 m). One says the home team had the ball, which the Pundit read from the moment's ball owner but the judge's context does not include.
- q052 (Spanish, what-if) hit the 25 s deadline. The Pundit wrote numbers as words in round 1 ("cincuenta y cinco por ciento") and "55 por ciento" in round 2. Only round 3 passed, which left too little time for the what-if. Fixed in commit `92b7322` (Pundit agent version 5): digits followed by "por ciento" / "per cent" now read as "55%", and the prompt and the Verifier's feedback show the digit form to copy. Re-asked live once afterwards, q052 passed in round 1 with its overlay ready at 14.3 s. Two other Spanish questions (q040, q046) also passed in round 1. The full 84-question eval was not re-run for this change.
