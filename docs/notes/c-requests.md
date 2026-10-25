# Stream C requests: deploying the live crew ("Ask the pundit")

For the coordinator. Stream C created no Azure resources; everything below is yours to create or decline.
Service: `POST /ask` → NDJSON AskEvents (`contracts/schemas/ask-event.schema.json`), image from `crew/Dockerfile`.

## 1. Where it runs: Container Apps, not a Foundry Hosted Agent (recommended)

| Option | Fit | Cost |
|---|---|---|
| **Container App `chalktalk-ask` in the existing `chalktalk-cae`** (Consumption, `minReplicas 0`, `maxReplicas 1`, 0.5 vCPU / 1 GiB, image from GHCR) | Runs the crew, the in-process MCP tools (sim + analytics) and the Verifier/Critic as one Python process, exactly as tested | $0 at demo traffic: the monthly free grant is 180,000 vCPU-s, 360,000 GiB-s and 2M requests. Scale-to-zero means a cold start of about 30 s (the match build), so warm it before a demo |
| Foundry Hosted Agent | GA (message AZ563596), and Korea Central supports Agents and the Responses API ([limits and regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)) | Compute is billed for active execution on top of tokens, and I found no published rate. The service also needs the whole sim/MCP Python stack in-process, so a hosted agent would only wrap the same container |

The agents themselves are Foundry Agent Service prompt agents (`chalktalk-ask-analyst|pundit|tactician`, gpt-4.1-mini), so the Foundry integration stays either way.

### Container App settings
- **Image:** `ghcr.io/manuareraa/chalktalk-ask:<sha>`. This needs a GHCR build workflow for `crew/Dockerfile`, like the mcp one (stream D or the coordinator); the pull options are in `b-mcp-image.md`.
- **Identity:** a system-assigned managed identity with **Azure AI User** (or Cognitive Services User) on `chalktalk-foundry`. `FoundryRunner` uses `DefaultAzureCredential`, which picks it up.
- **Probe:** `GET /healthz` on port 8080. Ingress is external, and the edge Worker routes `/api/ask` and `/api/ask/audio/*` to it, with streaming kept on (`X-Accel-Buffering: no`).
- **Env:**
  - `CHALKTALK_ASK_BACKEND=azure` (without it, the fakes run)
  - `AZURE_AI_PROJECT_ENDPOINT` (the `chalktalk` project endpoint)
  - `CHALKTALK_AGENT_VERSION=pundit=3`: the Pundit's latest instructions (silent cue marks, numbers in digits). The default is version 1 of every role.
  - `AZURE_SPEECH_KEY` (secret) and `AZURE_SPEECH_REGION=koreacentral`
  - `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` (secret) for Content Safety, which derives its endpoint from the OpenAI one
  - the image already sets `CHALKTALK_SIM_HALF_MINUTES=5` and `CHALKTALK_ASK_PRELOAD=sim-7`
- **Agents:** they are synced already (analyst 1, pundit 3, tactician 1). After any instruction change, run `python -m chalktalk_crew.ask sync` (a data-plane call, not a resource) and bump `CHALKTALK_AGENT_VERSION`.

## 2. Content Safety: no new resource
Prompt Shields and the text check run on the existing `chalktalk-foundry` endpoint (`https://chalktalk-foundry.cognitiveservices.azure.com`) with its key. This was verified live: the attack question was refused with a `refusal` event (`prompt_shield`). To use a separate endpoint, set `CHALKTALK_CONTENT_SAFETY_ENDPOINT`.

## 3. Tracing: optional App Insights, free ingest only
`configure_tracing` sends OpenTelemetry spans when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, and otherwise uses the project's connected App Insights if there is one. Each `done` event carries its `trace_id` either way. If you add App Insights, use a workspace-based one with a **daily cap of 0.1 GB**, which stays within the 5 GB/month free ingest. Without it, tracing is off and nothing breaks.

## 4. Voice Live compatibility (for later, not needed now)
The crew speaks through Azure Speech TTS with word boundaries, and the strokes land on those word times. Voice Live returns the same timing:
- Endpoint: `wss://<resource>.services.ai.azure.com/voice-live/realtime?api-version=2026-04-10&model=<model>`.
- Send `session.update` with `"output_audio_timestamp_types": ["word"]`.
- It then streams `response.audio_timestamp.delta` events `{audio_offset_ms, audio_duration_ms, text, timestamp_type: "word"}`, followed by `response.audio_timestamp.done`. This works with Azure voices only.
- These map one-to-one onto our word marks, so `ask/speak.py` could swap backends without changing the overlay.
- Docs: [Voice Live how-to](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-how-to) and [region support](https://learn.microsoft.com/azure/foundry/reference/region-support). It needs a Foundry resource (Speech resources do not integrate with Agent Service).
- **Not verified:** whether gpt-4.1-mini is a Voice Live model in koreacentral. Check before relying on it.

## 5. Dependencies
- **`what_if` (PR #68, `stream/b-what-if`)** must merge for the Critic's counterfactuals. Until then the crew skips the ghost-stroke stage and still answers.

## 6. Cost
- **Tokens:** 3 live answers used 8 calls, 11,310 prompt and 689 completion tokens, so **$0.0056 for 3 answers (about $0.002 each)** at gpt-4.1-mini rates.
- **Caps:** `max_tokens` 300 per call and at most 5 tool calls per answer, plus a 25 s deadline. Answers are cached per moment, so a replayed question costs nothing.
- **Speech:** F0, free.
- **Container App:** about $0 inside the free grant.
- **GHCR:** free.
- **App Insights:** optional, free under its cap.
