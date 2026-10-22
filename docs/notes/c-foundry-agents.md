# Stream C: the crew on Foundry Agent Service (M4)

`CHALKTALK_AGENTS=foundry` runs the crew's four roles as PromptAgents in the Foundry project
`chalktalk`, through Microsoft Agent Framework (`agent-framework-foundry`). The default is
`local`, the in-process crew, which also serves as the fallback for every role. Code:
`crew/src/chalktalk_crew/foundry_agents.py`.

| agent | what the model decides | what stays deterministic |
|---|---|---|
| `chalktalk-director` | ranks candidate moments, may drop repeats | candidates come from the event rules; unknown ids fall back to all |
| `chalktalk-analyst` | which planned tool to call, via local function tool `run_analytics` | tool arguments come from the moment; skipped tools run in-process |
| `chalktalk-pundit` | the script template (`llm.SYSTEM_PROMPT`) | slot values and strokes are filled from tool results |
| `chalktalk-verifier` | reports the verdict | `verify_overlay` re-runs the tools; its gate is the one the overlay carries |

Coordinates and numbers never come from a model. When an agent fails (auth, network or a
malformed answer), that role runs in-process, and the run log records it under
`agents.fallbacks`. The same log counts `agents.runs` per role.

## Azure: nothing new is created

- Agent definitions are data-plane objects in the existing project, and they cost nothing until
  they run. Every role uses the existing `gpt-4.1-mini` deployment.
- Auth is Entra ID. Agent Service does not accept API keys: `DefaultAzureCredential` uses
  `az login` locally and managed identity on Azure.
- **Needed:** the role **Azure AI User** for the developer, on `chalktalk-foundry`. It is free.
  Without it, `az login` gets 403 on `agents/read`, `connections/read` and `deployments/read`.
  The coordinator was asked on 2026-10-22. Until it is granted, every role falls back, and the
  run still completes.
- **Tracing:** `configure_tracing` turns on Agent Framework's OpenTelemetry spans, covering
  every agent run and tool call. When the project has an Application Insights connection, the
  spans are exported there and show under Tracing in the Foundry portal. Without one, they stay
  local (`CHALKTALK_TRACE_CONSOLE=1` prints them). No App Insights resource is requested; see
  CLAUDE.md on free ingest.

## Run it (manual only; CI and tests use a scripted stand-in)

```bash
uv sync --package chalktalk-crew --extra foundry --inexact
set -a; . ~/.config/chalktalk/azure.env; set +a
uv run python -m chalktalk_crew.foundry_agents show      # the four definitions, offline
uv run python -m chalktalk_crew.foundry_agents sync      # creates version N of each agent
CHALKTALK_AGENTS=foundry CHALKTALK_AGENT_VERSION=1 CHALKTALK_MAX_TOKENS=300 \
  uv run python -m chalktalk_crew run --half-minutes 3 --max-moments 1
```

Cost: each overlay takes about 4 to 6 agent runs: one Director run per match, then one Analyst
run (with a tool round trip), one Pundit run and one Verifier run per overlay. With prompts of
about 1.5k tokens and output capped at 300, that is under $0.005 per overlay at
gpt-4.1-mini prices. The run log's `llm.est_cost_usd` sums every agent run, and
`--budget-usd` stops the run when that sum passes the limit.

## Smoke result

Pending the role. It will be filled in after the first live run.
