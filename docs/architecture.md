# Architecture

ChalkTalk turns a synthetic football match into short studio breakdowns: a pundit speaks, and each arrow, line or zone draws on the 3D pitch on the word that names it. The data is fully synthetic.

Two rules shape every part of the system:
- **Facts come from tools, never from a model.** Coordinates, distances and percentages are computed by deterministic Python code. The LLM only picks, phrases and orders. Every spoken number is bound to the `tool_call` that produced it, and a verifier re-runs the tools before an overlay is released.
- **Free tier by design.** Heavy data (25 Hz tracking frames, audio) is precomputed into static files. Servers carry only low-rate control messages.

## Overview

```
                     ┌──────────────────────── Azure (chalktalk-rg) ────────────────────────┐
 sim (seed) ──────►  │ crew: Director → Analyst (MCP tools) → Pundit → Speech → Verifier    │
 match package       │       Foundry Agent Service, gpt-4.1-mini      Azure AI Speech (F0) │
   │                 │ evals: Foundry evaluations (groundedness, tolerance, cue timing)    │
   │                 └───────────────────────────────┬──────────────────────────────────────┘
   │                                                 │ POST /api/overlay (verified only)
   ▼                                                 ▼
 ┌──────────────── Cloudflare Worker `chalktalk` (free plan) ────────────────┐
 │ static assets: web build, /matches/<id>/ chunks, fixtures                 │
 │ /api/match/:id   manifest      /api/match/:id/control   play/pause/seek   │
 │ /ws/match/:id ── MatchHub Durable Object: match clock, frames, overlays   │
 └───────────────────────────────────────┬──────────────────────────────────┘
                                         │ WebSocket (frames, overlays, clock)
                                         ▼
                      web (React + three.js): Broadcast, Player and Show surfaces
```

## Components

| Path | Language | Role | Notes |
|---|---|---|---|
| `contracts/` | JSON Schema | The single source of truth for `frame`, `event`, `overlay` and hub messages. Pydantic and TypeScript types are generated, and CI fails if they drift. | `scripts/gen_contracts.sh` |
| `sim/` | Python | A seeded synthetic match generator. It writes a match package: a manifest, events, and 10 s gzip chunks of 25 Hz frames. | [b-match-package](notes/b-match-package.md) |
| `core/` | Python | Geometry and analytics: pitch control, lines, gaps, pressing and passing options. | |
| `mcp/` | Python | The Analyst's tools as an MCP server (stdio or streamable HTTP). It can run as a Container App that scales to zero. | [b-mcp-server](notes/b-mcp-server.md) |
| `crew/` | Python | The four-role crew. It runs as Foundry PromptAgents through Microsoft Agent Framework, falling back to an in-process crew per role. It caches verified overlays, audio and cue sheets, and posts them to the edge. | [c-foundry-agents](notes/c-foundry-agents.md), [c-e2e-cli](notes/c-e2e-cli.md), [c-live-post](notes/c-live-post.md) |
| `evals/` | Python | Three custom evaluators, run locally in CI and in Foundry. | [c-evals-foundry](notes/c-evals-foundry.md) |
| `vision/` | Python | Auto-eventing from rendered video: detection, tracking and calibration, then event rules (shot, goal, pass). It runs locally on a 4 GB GPU. | [e-s5-vision](notes/e-s5-vision.md), [e-m9-events](notes/e-m9-events.md) |
| `workers/edge/` | TypeScript | One Worker: static assets, the API, and one `MatchHub` Durable Object per match. | [d-edge](notes/d-edge.md) |
| `web/` | TypeScript | React 19, react-three-fiber pitch, and telestration strokes timed by the audio clock. | [a-demo-path](notes/a-demo-path.md) |
| `infra/` | Bicep | The Container Apps environment and the `mcp` app (consumption, `minReplicas` 0). | [d-azure-deploy](notes/d-azure-deploy.md) |

## How a breakdown is made

1. **Director.** Event rules propose candidate moments. The model ranks them and may drop repeats.
2. **Analyst.** It chooses which planned tool to call. Arguments come from the moment, and the tools run deterministically.
3. **Pundit.** The model picks the script template. Numbers and strokes are filled from tool results.
4. **Speech.** Azure AI Speech returns audio, word boundaries and SSML bookmarks. Each stroke's cue snaps to the start of the word that names it.
5. **Verifier.** It re-runs the tools and checks every claim against them. Only overlays that pass the gate are cached and posted.
6. **Edge.** The Worker stores the overlay and broadcasts it to the match's viewers.
7. **Web.** The browser plays frames against its own playhead and starts each stroke when the audio reaches its cue.

Each role falls back to the in-process version on any agent error, and the run log records the fallback.

## Live clock (MatchHub)

- The first viewer starts the match clock. When the last viewer leaves, the clock pauses and the alarm stops, so an unwatched match costs nothing.
- While someone watches, one alarm per second sends 25 frames and any events. That is about 3,600 Durable Object requests per watched hour, well under the free 100k a day.
- The producer controls (play, pause, seek, rate) and overlay posts need a shared secret header.

## Cost controls

- **Cloudflare:** free plan only. The account is shared with another project, so the limits are account-wide. `scripts/cf_usage.py` checks the daily usage: [coord-cloudflare](notes/coord-cloudflare.md).
- **Azure:** a $100 credit in total.
  - Foundry is AIServices S0, with pay-per-token `gpt-4.1-mini` at 20K TPM.
  - Speech is F0, the free tier.
  - The optional `mcp` Container App scales to zero.
  - There is no ACR, no GPU, no provisioned throughput and no Log Analytics.
  - A $60 budget sends alerts.
  - Tests and CI use fake clients. Live runs cap `max_tokens`, have a `--budget-usd` stop, and cache every output, so a moment is generated once.

## Key decisions

See [decisions.md](decisions.md). In short:
- One Worker instead of three.
- TypeScript at the edge, Python everywhere else.
- JSON Schema contracts.
- Fully synthetic data.
- Media as Workers static assets.
