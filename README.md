# ChalkTalk

An AI pundit crew that explains a football match by drawing on the pitch. Every arrow, line and space appears on the word that names it. Made for the Microsoft "Inside the Game" hackathon, on fully synthetic match data.

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
