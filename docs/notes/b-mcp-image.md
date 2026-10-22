# B → coordinator: the MCP image is ready to deploy

**Status (2026-10-22): ready.** Stream B creates nothing in Azure; the deploy is yours.

## Image
- `ghcr.io/manuareraa/chalktalk-mcp:latest`, plus `:sha-<short>` for every push to `main`.
  - It is built by `.github/workflows/mcp-image.yml` whenever `mcp/`, `core/`, `sim/` or `contracts/` change.
  - The first main build is `sha-27bb5c2`. Pin a sha tag for the demo rather than `latest`.
  - The newer tools arrive in the next image after each PR merges: `ghost` (#25), `var_offside` (#26), and `half_time` and `catch_up` (#27).
- The image is about 330 MB and runs as non-root. Its entrypoint serves streamable HTTP on `0.0.0.0:8000`.
  - `POST /mcp` is stateless MCP with JSON responses.
  - `GET /healthz` returns `{"status":"ok","version":…}`.
- **Pulling:** a GHCR package pushed from a private repo is private by default. Pick one:
  1. Make the package public (GitHub → Packages → chalktalk-mcp → visibility). It contains code only: no data, no keys.
  2. Or give the Container App a registry credential for `ghcr.io`: a PAT with `read:packages` only, stored as a Container Apps secret.

## Container App request (unchanged from `b-mcp-server.md`)
- Consumption profile only, with `minReplicas: 0` and `maxReplicas: 1`, at 0.5 vCPU and 1 GiB.
  - It costs about $0 at demo use, inside the free grant. If it were kept awake around the clock, the worst case is about $35 a month.
- Target port 8000. Liveness probe on `/healthz`.
- Set env `CHALKTALK_MAX_MATCHES=2`. Optionally set `CHALKTALK_PACKAGES`; without it, matches are regenerated on first use, about 25 s for a full match.
- **The server has no auth.** Use internal ingress so the crew calls it inside the environment, or put Easy Auth or an API key at the ingress.

## Smoke test
```bash
docker run --rm -p 8000:8000 -e CHALKTALK_SIM_HALF_MINUTES=1 ghcr.io/manuareraa/chalktalk-mcp:latest
curl -s localhost:8000/healthz
curl -s -X POST localhost:8000/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```
`tools/list` returns 21 tools on `main` today, 25 once #25, #26 and #27 merge. Checked on 2026-10-22 against the server run from source: `initialize`, `tools/list` and a `tools/call` all answer as JSON.

Crew client config: point it at `https://<app>/mcp` using the streamable HTTP transport.
