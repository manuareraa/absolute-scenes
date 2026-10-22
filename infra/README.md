# Infra (stream D)

The Azure resources are declared in Bicep and deployed with `azd`. The list is in BUILD-PLAN §7:
- Foundry project and model deployments
- Speech
- Container Apps environment, plus the `mcp` app and the post-match Job
- Container Registry
- Log Analytics and App Insights
- A managed identity

Cloudflare resources are configured in `workers/edge/wrangler.jsonc`. Free plan only.
