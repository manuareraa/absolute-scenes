# Stream C: Azure clients for the crew

The crew talks to Azure only through two interfaces. Both have deterministic fakes, which are the
default and the only thing tests and CI use:
- `chalktalk_crew.llm.LLMClient.draft(DraftRequest) -> str`: the Pundit writer.
  Live: `AzureFoundryLLMClient`, chat completions on the Foundry deployment over plain HTTPS
  (stdlib only, no SDK). It caps `max_tokens`, retries only 429 and 5xx, and counts tokens in
  `.usage` (calls, prompt and completion tokens, estimated USD at gpt-4.1-mini list prices).
- `chalktalk_crew.speech.SpeechClient.synthesize(ssml) -> SpeechResult`.
  Live: `AzureSpeechClient` (Speech SDK). It returns MP3 audio (24 kHz, 48 kbit/s mono),
  WordBoundary timings, and bookmark offsets snapped to the start of the next word. The raw
  bookmark offsets stay in `extra`.

## Env vars
Keys are read from the process environment only and are hidden from `repr`. Load them with
`set -a; . ~/.config/chalktalk/azure.env; set +a`.

| Var | Meaning |
|---|---|
| `CHALKTALK_CREW_BACKEND` | `fake` (default) or `azure`, for both clients |
| `CHALKTALK_LLM_BACKEND`, `CHALKTALK_SPEECH_BACKEND` | override per client |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY` | Foundry (`CHALKTALK_FOUNDRY_ENDPOINT` / `_DEPLOYMENT` win if set) |
| `CHALKTALK_FOUNDRY_API_VERSION` | default `2024-10-21` |
| `CHALKTALK_MAX_TOKENS` | completion cap, default 300 (a script template is about 80 tokens) |
| `AZURE_SPEECH_REGION`, `AZURE_SPEECH_KEY` | Speech F0 (`CHALKTALK_SPEECH_REGION` wins if set) |
| `CHALKTALK_SPEECH_VOICE` | default `en-GB-RyanNeural` (sets the SSML locale too) |
| `CHALKTALK_LEAD_MS` | stroke lead before the cue word, default 150 |

## Running live
The Speech SDK is an optional extra (`chalktalk-crew[azure]`), so `uv sync --frozen` in CI never
installs it. To run live, add it for the one command:

```bash
set -a; . ~/.config/chalktalk/azure.env; set +a
CHALKTALK_CREW_BACKEND=azure uv run --with azure-cognitiveservices-speech python your_script.py
```

Smoke test (Oct 22), one analyst/home overlay with four beats: 336 prompt tokens plus 74
completion tokens is about $0.00025. The gate passed with real WordBoundary timings.
