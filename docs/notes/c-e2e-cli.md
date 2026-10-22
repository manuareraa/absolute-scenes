# Stream C: end-to-end crew CLI

`python -m chalktalk_crew run` turns a seeded synthetic match into verified, cached overlays.

```
sim (seed) -> Director moments -> CoreToolClient (chalktalk_mcp Tools, in-process)
           -> Pundit (Foundry or fake) -> Speech (Azure or fake) -> Verifier -> cache
```

## Run it
- Fakes (free, the default): `uv run python -m chalktalk_crew run --half-minutes 3`
- Live (manual only, never in CI):
  ```
  set -a; . ~/.config/chalktalk/azure.env; set +a
  CHALKTALK_CREW_BACKEND=azure uv run --with azure-cognitiveservices-speech \
    python -m chalktalk_crew run --seed 7 --max-moments 6 --lenses casual,analyst \
    --sides home,away --cache <dir>
  ```
- Options: `--seed`, `--half-minutes` (45), `--max-moments` (6), `--lenses`, `--sides`,
  `--lang`, `--cache` (`.chalktalk-cache`), `--budget-usd` (0.25: stops generating past it),
  `--retry-rejected`.

## Cache (`<cache>/<match_id>-<digest8>/`)
| path | what |
|---|---|
| `overlays/<id>.json` | verified overlays only (gate passed, schema-valid) |
| `rejected/<id>.json` | overlays the gate failed; not retried unless `--retry-rejected` |
| `audio/<id>.mp3` | the spoken script; `script.audio_url` is `audio/<id>.mp3` |
| `cues/<id>.json` | cue sheet: cue, offset, the word it lands on, stroke, stroke start |
| `runs/<ts>.json` | run log: generated/cached/rejected/skipped/failed, tokens, speech chars, cost |

A cached or rejected moment is never sent to Foundry or Speech again. A moment whose Azure call
fails is logged under `failed` and left uncached, so the next run retries it. The digest in the
folder name means a change to the sim gives a fresh folder rather than stale overlays.

## Analytics adapter (`crew/src/chalktalk_crew/core_tools.py`)
| crew tool | MCP tool | value | stroke |
|---|---|---|---|
| line_gap | `line_gap(defence_midfield)` | m | the arrow between the lines |
| shape_compactness | `team_shape` | m2 | hull zone |
| offside_line | `offside_line` | m from halfway | offside line |
| pitch_control | `pitch_control` on a 30x24 m zone round the ball | share x 100 = % | zone |
| pressing_intensity | `pressing_intensity` over the 5 s before | prob x 100 = % | ring (4 m) on the ball |
| pass_options | `pass_options` (scans back 3 s for a carrier) | lane count | first pass lane |
| xg | `shot_xg` | xG | the shot arrow |

A tool that cannot answer (nobody on the ball) raises `ToolError` and is dropped from the
breakdown; if every tool drops, the moment is skipped (`NoEvidence`).

## Pundit quality fixes found by the live run
The first live run passed the gate but read badly: the model spoke tool names ("line_gap"),
left values out and put cues before "Their". Now:
- `check_template` also rejects raw snake_case names, slots never spoken, and a cue placed
  right before a number slot.
- The prompt gives the drawn noun per tool and a worked example.
- `fix_slot_names` repairs misspelt slots (`{xG}` -> `{xg}`, a single unknown -> unspoken).
- One repair call with the exact error, then the rule-based writer as fallback.

## Live demo run (Oct 22)
Seed 7, 45-minute halves, 6 moments x casual/analyst x home/away = 24 overlays.

| | |
|---|---|
| verified overlays | 24 / 24 (0 rejected, 0 failed) |
| model-written / rule-based fallback | 18 / 6 |
| Foundry calls (incl. repairs) | 37 |
| tokens | 20,469 prompt + 2,406 completion |
| est. cost | **$0.012** (gpt-4.1-mini list price); Speech F0 is free (4,991 chars) |
| re-run | 0 calls, $0 (all 24 cached) |
| audio | 24 MP3s, median 13 s, 2.6 MB in total |
| wall clock | about 4 to 5 minutes, mostly Speech F0 |

Speech F0 once returned `ServiceTimeout` under load; the client now retries that and
throttling (429) with backoff.
