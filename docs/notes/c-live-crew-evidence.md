# Live crew ("Ask the pundit"): evidence

Every number below was measured; none is estimated.

**The evidence run (2026-10-25)**
- **Setup:** a fixed set of 8 questions (5 en-GB, 3 es-ES; 4 of them ask what the defence should have done, which triggers the Tactician), asked once each, in one process. Script: `live8.py`, in the session scratchpad, not committed.
- **Config:** gpt-4.1-mini in koreacentral; Foundry agents analyst v1, pundit v3, tactician v1 (`CHALKTALK_AGENT_VERSION=pundit=3`); the shipped show sim-7 on 5-minute halves; what_if from PR #68.
- **Output:** the full NDJSON is in `c-live-crew-ask-live.ndjson`. Every number in §1–§5 was read from it with a short Python pass.

## The coordinator's five measures

### 1. Verifier rejections
- **Round 1:** 1 of 16 Pundit claims rejected (6%). Fixed by round 2: 1 of 1, and all 8 answers passed the gate.
- **How measured:** count of `verdict` events with `round == 1` and `ok == false`, then whether that answer's round-2 verdicts were all `ok`.
- **Earlier runs (same day, Pundit v1, 5 runs of 3 questions):** 0 of 15 drafts rejected.

### 2. One logged rejection (the es-ES question at t=410000 ms)

| | |
|---|---|
| Question | "¿Qué debería haber hecho la defensa aquí?" |
| Round-1 claim | "La defensa debería haber incrementado la presión sobre el balón, que aquí era solo del **tres por ciento**, para dificultar el pase" |
| Tool value | `pressure` = 0.03, spoken form "3%" |
| Verifier reason | `write 'por ciento' as digits, exactly as the result's 'say' field` |
| Round-2 rewrite | "La defensa debería haber aumentado la presión al **3%** sobre el balón y reducir la distancia de 1,7 m para limitar las opciones de pase, que son 4" |

Every number in the rewrite matched a tool call, so the answer shipped.

### 3. Counterfactuals: 7 proposals, 1 accepted by the Critic
- **How measured:** `counterfactual` events. Each proposal is a Tactician move set re-run through `what_if`; its metrics are the tool's before/after values.
- **Accepted** (t=530680 ms, "What should the defence have done about that gap?"): "away number 3 moves over".
  - pitch_control 0.589 → 0.608 and line_gap 8.55 m → 8.55 m (`tc_what_if_2c7386d69ad5`).
  - It shipped as a dashed ghost stroke, and the spoken line was "pitch control goes from 59% to 61%".
- **Rejected** (t=410000 ms): "Close down ball carrier quickly by moving A05 closer and supporting with A04".
  - pitch_control 0.786 → 0.730, line_gap 14.49 m → 14.42 m, pressure 0.03 → 0.03, obso 0.0055 → 0.0067 (`tc_what_if_0f2bb9c593ec`).
  - Control fell, so the Critic rejected it.
- **Earlier runs, same day:** 2 of 5 accepted on 45-minute halves; 0 of 4 on the 5-minute show, each rejected because line_gap widened.

### 4. Time from question to first stroke: median 17.8 s
- **Spread:** 7 answers that drew a stroke; min 11.9 s, max 22.7 s. The 8th answer (pressure 0%) had nothing to draw.
- **How measured:** the `overlay` event's `t_ms` (when the overlay and its audio are ready to play), plus the first stroke's cue `offset_ms` in that audio, minus its `lead_ms`.
- **Breakdown:** the overlay arrived after a median of 14.2 s (10.8 to 19.2 s, all within the 25 s deadline). The rest is how far into the spoken answer the first named thing falls.

### 5. Foundry trace ids, one per run (from each `done` event)
6a544dfaaa7640d99c9343a6629bd27f, 3deec1a19bb2436bb394844b83025b97, e683f8c9d8884e74addea11b72975c21, cf9f482575494aaa9fb25ec39ad3e8ed, a14ee022c5934c3aa174ad14c8b4cadb, ce184b170ba4454ba3be1bb542dff005, a1f7df8575b946febdc67e94a0af6bb1, 2609bf91d8a8493a999c0b56e2dab12a, in question order.

## One line per feature
- **2026-10-25 · Open tool choice (Foundry Agent Service prompt agent with function tools).** Across 8 questions the Analyst chose 8 different tool sets itself (no fixed sequence), with 1 to 4 distinct tools each, from 8 of the offered tools (plus what_if for the Critic).
- **2026-10-25 · Verifier reject-and-rewrite.** 1 of 16 round-1 claims rejected, and 1 of 1 fixed in round 2 (§1–§2).
- **2026-10-25 · Critic over structured offsets (TacEleven, arXiv 2511.13326; TacticAI, Nature Communications 2024).** 1 of 7 what_if proposals accepted (§3). Coordinates come only from what_if.
- **2026-10-25 · Parallel Tactician draft.** The first proposal is drafted while the Pundit writes. The counterfactual question went from 23.8 s to 15.9 s in A/B runs, and to 13.3 s in this run.
- **2026-10-25 · Match warmed before the deadline (`warm`, `CHALKTALK_ASK_PRELOAD`).** This took about 27 s of match building out of the first ask on 45-minute halves. A preloaded container answered a fake ask in 21 ms.
- **2026-10-25 · Azure AI Content Safety (Prompt Shields + text analysis) on the existing AIServices endpoint.** The live attack question was refused with a `refusal` event (`prompt_shield`) before any agent ran.
- **2026-10-25 · Foundry tracing (OpenTelemetry via `azure-monitor-opentelemetry`).** Each `done` event carries a trace_id (§5).
- **2026-10-25 · Azure Speech word boundaries for stroke timing.** 8 of 8 answers passed the gate with audio, and their cue marks resolved to audio offsets (§4). Voice Live's word `response.audio_timestamp.delta` events are a drop-in source (`c-requests.md` §4).
- **2026-10-25 · Cost caps (max_tokens 300, at most 5 Analyst tool calls, a per-moment answer cache).** The 8 answers used 24 Foundry calls, 31,759 prompt and 2,056 completion tokens: **$0.016 in total, $0.002 per answer**.
- **2026-10-25 · Container image (`crew/Dockerfile`, fakes by default).** Size 468 MB. A fake ask in the container streamed a schema-valid answer, and the container used 51 MiB with sim-7 preloaded.
