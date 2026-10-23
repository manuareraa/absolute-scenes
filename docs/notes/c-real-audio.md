# Real audio for the Show fixture (stream C)

`python -m chalktalk_crew voice-show` (`crew/src/chalktalk_crew/voice.py`) gives `show-sim-7.json` real Azure Speech audio. This PR adds only the tool. The coordinator runs the commands below and commits the `web/` output on a `coord/` branch, because `web/` belongs to stream A.

## What gets voiced
- **Crew chapters** (4 moments × 3 lenses × 3 sides × 2 languages = 72):
  - The live `run` synthesizes each one with Speech F0, and caches its MP3 and word-snapped cues.
  - `voice-show` copies the cached MP3s next to the fixture.
- **Ghost and VAR chapters:**
  - These are built from tools and were timed by the fake speech client.
  - `voice-show` synthesizes their SSML and replaces their cues and words with the real timings.
  - Their text is the same across lenses and sides, so there are only 4 syntheses: ghost and VAR, each in en-GB and es-ES.
  - Results are cached in `<crew cache>/<match>-<digest8>/voiced/` by SSML hash, so a re-run costs no characters.
- **Half-time and catch-up summaries** have no script; the player shows them as data panels. They have no audio.

## Commands (run once B's sim-7 is final)
`--half-minutes` must match the live package, which is 5. Keys come from env; never print them.

```
set -a; . ~/.config/chalktalk/azure.env; set +a
C=.chalktalk-cache-real-audio

# 1. Crew overlays and MP3s: live Foundry gpt-4.1-mini plus Speech F0, capped at $0.50
CHALKTALK_AGENTS=foundry CHALKTALK_AGENT_VERSION=1 CHALKTALK_MAX_TOKENS=300 CHALKTALK_CREW_BACKEND=azure \
  uv run --with azure-cognitiveservices-speech python -m chalktalk_crew run \
  --seed 7 --half-minutes 5 --max-moments 4 --lenses casual,analyst,newcomer \
  --sides home,away,neutral --lang en-GB,es-ES --cache $C --budget-usd 0.50 > $C-run.json

# 2. Show fixture and producer queue from those overlays (stream A's builder, no Azure)
env -u CHALKTALK_CREW_BACKEND uv run python web/scripts/show_fixture.py --cache $C --half-minutes 5 \
  --out /tmp/show-sim-7.json --queue web/public/fixtures/queue-sim-7.json

# 3. Audio into the fixture: the 4 tool-chapter syntheses (Speech F0, no tokens)
CHALKTALK_SPEECH_BACKEND=azure uv run --with azure-cognitiveservices-speech \
  python -m chalktalk_crew voice-show --fixture /tmp/show-sim-7.json --cache $C \
  --half-minutes 5 --out web/public/fixtures
```

Step 3 writes `web/public/fixtures/show-sim-7.json` and `web/public/fixtures/show-sim-7/audio/*.mp3`. It prints a JSON log with these fields:
- `copied`, `synthesized`, `reused` and `missing`: overlay ids;
- `speech_characters`;
- `files`, `total_bytes` and `largest_bytes`;
- `cue_word_gap_max_ms`: the largest distance from a cue to a word start, which must be 0.

The tool refuses to write if any MP3 is over the 25 MiB Workers static-asset cap.

## Checks
- In `$C-run.json`:
  - `failed` and `skipped` should be empty.
  - `est_cost_usd` is the token spend.
  - `agents.fallbacks` should be 0.
- In the step 3 log:
  - `missing` should be empty. A crew chapter with no cached MP3 keeps its words but loses its `audio_url`, so it plays the stand-in voice.
  - `cue_word_gap_max_ms` should be 0.
- Rough size: at 48 kbit/s, about 6 KB per second of speech. 72 chapters of 15–25 s come to roughly 7–11 MB in total, with each file well under 1 MB.

## Cost estimate
- **Tokens:** 72 overlays × about $0.0012 (about 5 agent runs each, as measured in M10) ≈ $0.09. The `--budget-usd 0.50` cap stops the run long before $1.
- **Speech:** about 76 syntheses of about 400 characters each ≈ 30k characters. F0 includes 0.5M characters a month, so this is free.
