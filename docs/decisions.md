# Decisions

## Oct 22, 2026: M0
1. **One Worker instead of three.**
   - `workers/edge` serves the web build (static assets), `/api/*` and `/ws/match/:id`, which is the `MatchHub` Durable Object.
   - Why: fewer deploys and bindings, and static asset requests are free on the free plan.
2. **TypeScript at the edge, Python everywhere else.**
   - Python Workers do not fit the free plan's 10 ms CPU limit or the bundle size once numpy is included.
   - The edge only routes, stores and fans out.
3. **JSON Schema is the contract source of truth.**
   - Pydantic and TS types are generated from it, and CI fails if they drift.
   - Examples under `contracts/examples` are tested on both sides.
4. **Fully synthetic data.**
   - The rules (§4.7) require synthetic, football-realistic data.
   - IDSSE only calibrates and benchmarks the generator.
5. **Media on the free plan.**
   - Match chunks and HLS segments ship as Workers static assets: up to 20,000 files, 25 MiB each [I, to confirm in S6/D].
   - R2 is used only if it can be enabled without a payment method.
