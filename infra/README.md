# Infra (stream D)

Azure ($100 credit in total; only the coordinator creates resources, see `CLAUDE.md`):
- **Live, created by the coordinator with the CLI:** `chalktalk-foundry` (AIServices S0, `gpt-4.1-mini`)
  and `chalktalk-speech` (F0), in `chalktalk-rg`, koreacentral.
- **`main.bicep`:** a consumption-only Container Apps environment `chalktalk-cae` and the `mcp` Container App
  `chalktalk-mcp` (0 to 1 replicas, 0.25 vCPU / 0.5 GiB, image from GHCR). No ACR, no workload profiles,
  and no Log Analytics unless you pass a workspace that has a daily cap.
  - The deploy commands and the expected cost are in `docs/notes/d-azure-deploy.md`.
  - CI only compiles the Bicep (`.github/workflows/infra.yml`) and never signs in to Azure.
- **Later, only when needed:** the post-match Container Apps Job, in the same environment.

Cloudflare: `workers/edge/wrangler.jsonc`, free plan only.
