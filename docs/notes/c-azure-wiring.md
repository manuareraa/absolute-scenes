# Stream C → Coordinator: wiring Azure for the crew (M4)

The crew talks to Azure only through two interfaces, both with deterministic fakes used by
default (`CHALKTALK_CREW_BACKEND=fake`):
- `chalktalk_crew.llm.LLMClient.draft(DraftRequest) -> str` (Pundit writer on Foundry);
- `chalktalk_crew.speech.SpeechClient.synthesize(ssml) -> SpeechResult` (Azure AI Speech with
  SSML bookmarks and word boundaries; offsets in ms).

`chalktalk_crew.azure` has the adapter classes; they raise `NotImplementedError` until wired.

## Env vars (no keys; auth via `DefaultAzureCredential`, Azure CLI locally, managed identity on Azure)
| Var | Meaning |
|---|---|
| `CHALKTALK_CREW_BACKEND` | `fake` (default) or `azure` |
| `CHALKTALK_FOUNDRY_ENDPOINT` | Foundry project endpoint |
| `CHALKTALK_FOUNDRY_DEPLOYMENT` | model deployment name for the Pundit |
| `CHALKTALK_SPEECH_ENDPOINT` or `CHALKTALK_SPEECH_REGION` | Speech resource |
| `CHALKTALK_SPEECH_VOICE` | default `en-GB-RyanNeural` |
| `CHALKTALK_LEAD_MS` | stroke lead before the cue word, default 150 |

## Needed from the coordinator
- The resource names above once provisioned, and `az login` on the machine that runs the crew.
- Dependencies to add in stream C when wiring: `azure-identity`, `azure-cognitiveservices-speech`,
  and the Foundry client (`azure-ai-projects` or Agent Framework), kept to these.
