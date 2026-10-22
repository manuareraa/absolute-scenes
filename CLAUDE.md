# ChalkTalk: rules for every build session

ChalkTalk is an AI pundit that draws on a synthetic broadcast pitch. Every stroke lands on the word that names it.
- **Concept (locked):** `../plan/CONCEPT.md` (v5.1).
- **Build plan:** `../plan/BUILD-PLAN.md` (v2.1).

Both paths are relative to the main checkout `repo/`; the concept and plan sit in its parent folder.

## Worktrees (enforced)
- **Never edit the main checkout** (`repo/`). Make your worktree from the latest `main`:
  `scripts/new-worktree.sh stream/<letter>-<slug>`
  It creates the worktree in `repo-worktrees/` next to the main checkout. The coordinator uses `coord/<slug>`.
- **One session per worktree.** Never edit another session's worktree.
- **Branch names are checked:**
  - `stream/a-…` Web and 3D
  - `stream/b-…` Data, analytics and MCP
  - `stream/c-…` Crew, speech and evals
  - `stream/d-…` Platform
  - `stream/e-…` Vision
  - `coord/…` Coordinator
- **Only change paths your stream owns** (`owners.toml`). Both the pre-commit hook and CI check this.
  - If you need a contract change (`contracts/`) or something in another stream's paths, write a note in `docs/notes/<stream>-requests.md` on your branch and tell the coordinator.
- Never stash, `reset --hard`, `checkout --`, `clean`, or switch branches in a checkout you did not create.
- Remove your worktree only after its branch is merged.

## Flow
1. At the start of each work block, run `git fetch origin && git rebase origin/main`.
2. Commit small and often. Push your branch and open a PR into `main`.
3. The coordinator merges on green CI. Never push to `main` and never force-push `main`.
4. After a merge, start the next piece on a new branch from `origin/main`.

## Before you push
- Python: `uv run ruff check . && uv run ruff format --check . && uv run pytest`
- Node: `npm run typecheck && npm test && npm run build && npm run check:worker`
- Contracts: the JSON Schemas in `contracts/schemas` are the source of truth.
  - `scripts/gen_contracts.sh` regenerates the Pydantic and TypeScript types; never edit those by hand.

## Stack rules
- **Cloudflare free plan only.** One Worker (`workers/edge`, TypeScript) serves the web build, `/api/*`, and the `MatchHub` Durable Object (SQLite-backed). Limits: 10 ms CPU per request, 100k requests a day.
  - Static files (match chunks, HLS segments) go in Workers static assets; they are free.
  - No Workers Paid, no Containers, no Python Workers.
- **All Python compute runs on Azure:** the `mcp` tools and post-match jobs on Container Apps, and the crew on Foundry.
- **Data is fully synthetic**, as the hackathon rules require.
  - Real tracking data (IDSSE, Metrica) may only calibrate and benchmark `sim`. Never ship or show it.
  - No real footage, club names, crests, logos or PL marks.
- **Coordinates for drawing always come from tools, never from an LLM.** Every claim carries its `tool_call`.
- **Licences:** no AGPL or GPL code (no Ultralytics), no non-commercial models or data. Credit CC-BY sources in `docs/data-credits.md`.
- **Secrets:** never commit keys. Use `.dev.vars` and `.env` (both gitignored), `wrangler secret`, and Azure managed identity.

## Machine limits (one OOM crash already)
- 14 GB RAM. Use at most 2 subagents at a time. Read big files in ranges and pipe long output through `tail`.
- One GPU job (vision, headless render) at a time on the RTX 3050 (4 GB).
