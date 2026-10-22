# Stream C: languages (M7)

The crew speaks **en-GB** and **es-ES**, in all three lenses (casual, analyst, newcomer) and
for all three sides. Code: `crew/src/chalktalk_crew/lang.py` and `captions.py`.

| | en-GB | es-ES |
|---|---|---|
| voice (Speech F0) | `en-GB-RyanNeural` | `es-ES-AlvaroNeural` |
| decimal mark | `0.42` | `0,42` |
| team ref (home fans, away team) | "their" | "el rival" |

## Each language is its own script
- The Pundit writes the template in the language (`DraftRequest.lang`). The fake writer has
  Spanish phrases for every tool and lens, and a test checks each phrase against the template
  rules.
- `script.render` writes `xml:lang` and that language's `<voice>`, so the bookmarks come back
  from the voice that speaks them. `AzureSpeechClient` takes the voice from the SSML.
  `CHALKTALK_SPEECH_VOICE` still overrides the voice for its own language.
- Numbers are spoken in the locale's form (`format_value(value, unit, lang)`). The Verifier
  grounds against that same form, so "11.7" in a Spanish script fails the gate.
- Claims, strokes and geometry are the same in every language. Only the words and the cue
  timings change.

## Captions
Each verified overlay also gets `captions/<overlay id>.vtt` in the cache, built from the TTS
word timings, with punctuation restored from the script text. It is a sidecar file, so the
overlay contract is unchanged (`Script` allows no extra properties). If the web app wants the
captions inline, that is a contract request for the coordinator.

## Generated once
The overlay id ends in the language (`ov-<moment>-<lens>-<side>-es-ES`), so the cache keys
each language on its own. A second run sends nothing to Foundry or Speech.

```bash
uv run python -m chalktalk_crew run --lang en-GB,es-ES --lenses casual,analyst,newcomer
```

## Smoke result (2026-10-22, Speech F0, free)
One es-ES overlay, with the fake writer and live Speech (100 characters):
"El rival deja un hueco entre líneas de 11,7 metros. Nuestro equipo tiene el pase, una de
6 opciones." The gate passed. Cue `k1` landed on "hueco" at 975 ms and `k2` on "pase" at 5350 ms.
Azure times a number and its unit as one word ("11,7 metros"), and the captions handle that.
Cost: $0.
