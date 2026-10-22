# Stream D → coordinator: deploy the `mcp` Container App

The code is `infra/main.bicep` (PR stream/d-infra). Nothing has been run. **The coordinator runs these commands.**

## What it creates (resource group `chalktalk-rg`, koreacentral)
| Resource | Type | Settings |
|---|---|---|
| `chalktalk-cae` | Container Apps environment | Consumption only: no workload profiles, no zone redundancy. App logs **off** (no Log Analytics). |
| `chalktalk-mcp` | Container App | Image `ghcr.io/manuareraa/chalktalk-mcp`, port 8000, `minReplicas` 0, `maxReplicas` 1, 0.25 vCPU / 0.5 GiB, liveness and readiness on `/healthz`, HTTP scale rule (20 concurrent). Env: `CHALKTALK_MAX_MATCHES=1`, `CHALKTALK_SIM_HALF_MINUTES=5`. External ingress, limited to the CIDRs you pass. |

No ACR, no GPU, no workload profiles and no Log Analytics.

## Before you deploy
1. Merge the GHCR PR (stream/d-mcp-image) and let `mcp-image` push `ghcr.io/manuareraa/chalktalk-mcp:latest` and `:sha-<short>`.
2. The package is private, because the repo is private. Choose one:
   - **(simplest)** GitHub → Packages → `chalktalk-mcp` → Package settings → Change visibility → Public. The image holds no secrets and only synthetic data.
   - **or** keep it private and pass a classic PAT with only `read:packages`, as `registryUsername` and `registryPassword` below. Do not paste it into notes.
3. Register the provider once (free): `az provider register -n Microsoft.App --wait`

## Deploy (exact commands, from the repo root)
```bash
az account show --query "{sub:name, id:id}" -o table      # check the subscription
MYIP=$(curl -s https://api.ipify.org)
TAG=sha-XXXXXXX                                            # the tag the mcp-image run pushed
az deployment group what-if -g chalktalk-rg -f infra/main.bicep \
  -p image=ghcr.io/manuareraa/chalktalk-mcp:$TAG allowedCidrs="[\"$MYIP/32\"]"
az deployment group create -g chalktalk-rg -n chalktalk-mcp -f infra/main.bicep \
  -p image=ghcr.io/manuareraa/chalktalk-mcp:$TAG allowedCidrs="[\"$MYIP/32\"]" \
  --query properties.outputs.mcpUrl.value -o tsv
```
- For a private package, add `registryUsername=manuareraa registryPassword=$GHCR_READ_TOKEN`.
- Smoke test: `curl -fsS https://<fqdn>/healthz`. The first call after idle takes a cold start of about 10–20 s. Generating `sim-7` on first use takes a few seconds more.
- The MCP endpoint is `https://<fqdn>/mcp`. Point the crew at it.

### About the IP allowlist
The MCP server has no auth (see `docs/notes/b-mcp-server.md`), so the default deploy only lets your machine in.
- When the crew runs as a **Foundry hosted agent**, its outbound IPs are not fixed. Before that demo, choose one:
  - redeploy with `allowedCidrs="[]"` (open, read-only tools on synthetic data; a scan that wakes the replica costs cents), or
  - add auth at the ingress (Easy Auth). That is a later stream D PR if you want it.

## Expected monthly cost: **about $0**
Container Apps consumption, list prices to check on the Azure pricing page:
- Active: about $0.000024 per vCPU-second and $0.000003 per GiB-second.
- Scaled to zero: nothing.
- Free grant per subscription per month: 180,000 vCPU-s, 360,000 GiB-s and 2M requests.

| Item | Estimate |
|---|---|
| Environment (consumption only) | $0, no base fee |
| `mcp` at 0.25 vCPU / 0.5 GiB | The grant covers about **200 active replica-hours a month**. A replica stays up about 5 min after the last request (cooldown). Demos and tests (under 50 h) cost **$0**. |
| Beyond the grant | about $0.027 per active hour. Even always-on (730 h) would be about $14 a month. `minReplicas` 0 prevents that. |
| Requests | far under 2M → $0 |
| Logs | off → $0. Use `az containerapp logs show -g chalktalk-rg -n chalktalk-mcp --follow` for live console logs. |
| Egress | JSON tool replies, MBs a month → about $0 |

If you want stored logs later, create a Log Analytics workspace with `--quota 0.1` (a 0.1 GB daily cap, inside the 5 GB free ingest). Then pass `logAnalyticsCustomerId` and `logAnalyticsSharedKey`.

## Tear down
```bash
az containerapp delete -g chalktalk-rg -n chalktalk-mcp --yes
az containerapp env delete -g chalktalk-rg -n chalktalk-cae --yes
```
