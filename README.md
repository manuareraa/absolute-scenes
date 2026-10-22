# ChalkTalk

An AI pundit crew that explains a football match by drawing on the pitch. Every arrow, line and space appears on the word that names it. Made for the Microsoft "Inside the Game" hackathon, on fully synthetic match data.

- **Live:** https://chalktalk.inspectmate-logs.workers.dev (the studio show: `/?surface=show&lens=analyst&side=away`)
- **How it works:** [docs/architecture.md](docs/architecture.md)
- **Demo click path:** [docs/notes/a-demo-path.md](docs/notes/a-demo-path.md)

The pundit crew runs on Azure AI Foundry Agent Service (`gpt-4.1-mini`) with Azure AI Speech for timed audio. Its tools are deterministic Python behind an MCP server, so every number on screen comes from a tool call, and a verifier re-runs the tools before anything is shown. Foundry evaluations score claim groundedness, numeric tolerance and cue timing. A Cloudflare Worker with a Durable Object serves the web app and runs the live match clock.

## Try it locally (free, no cloud keys)
```bash
uv run python -m chalktalk_sim generate --seed 7 --half-minutes 5 --demo --out ./packages
uv run python -m chalktalk_crew run --half-minutes 3      # fake LLM and speech, cached overlays
npm run build --workspace web && node workers/edge/scripts/assemble.mjs --packages ./packages
npm run dev --workspace workers/edge                      # http://localhost:8787
```

## Layout
| Path | What |
|---|---|
| `contracts/` | JSON Schemas (source of truth), generated Pydantic and TypeScript types, contract tests |
| `core/` `sim/` `mcp/` | Geometry and analytics, the synthetic match generator, MCP tools (Python) |
| `crew/` `postmatch/` `evals/` | Agent crew, speech, post-match shows, Foundry evaluations (Python) |
| `vision/` | Auto-eventing from rendered video (Python) |
| `workers/edge/` | Cloudflare Worker: web assets, API, `MatchHub` Durable Object (TypeScript) |
| `web/` | React app and 3D pitch |
| `infra/` | Azure Bicep and azd |
| `scripts/` | Codegen, worktree helper, path checks |

## Develop
```bash
uv sync          # Python 3.12 workspace
npm ci           # Node workspaces
uv run pytest && npm test
npm run dev --workspace web            # http://localhost:5173
npm run dev --workspace workers/edge   # http://localhost:8787
```

Contributors and build sessions should read [CLAUDE.md](CLAUDE.md) first.

## Licence
MIT. Data and asset credits are listed in [docs/data-credits.md](docs/data-credits.md).
