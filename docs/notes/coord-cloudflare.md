# Cloudflare: deploy and free-tier watch (coordinator)

## Live
- Worker `chalktalk`: https://chalktalk.inspectmate-logs.workers.dev (free plan, deployed 2026-10-22).
  - The `inspectmate-logs` part is the account-wide workers.dev subdomain. Do not rename it: that
    would change the other project's URLs.
- Assets: web build plus match `sim-7` (`--seed 7 --half-minutes 5 --demo`), assembled by
  `node workers/edge/scripts/assemble.mjs --packages <dir>`.
- Secret `OVERLAY_SECRET` is set. Its value and the URL are in `~/.config/chalktalk/edge.env`
  (mode 600, outside the repo). Load with `set -a; . ~/.config/chalktalk/edge.env; set +a`.

## The account is shared
The same Cloudflare account runs InspectMate (Workers `inspectmate-console`, `inspectmate-learning`,
`inspectmate-logs`, 2 D1 databases, 1 R2 bucket). Free-plan limits are per account, per UTC day:

| Limit | Free | InspectMate peak (7 days) |
|---|---|---|
| Worker requests | 100,000 a day | about 3,000 |
| Durable Object requests | 100,000 a day | 0 (it has no DOs) |
| Durable Object duration | 13,000 GB-s a day | 0 |

Absolute Scenes' cost: static assets are free. Each `/api/*` or `/ws/*` hit is one Worker request. While
someone watches a match, its MatchHub alarm costs one DO request per second (3,600 per watched
hour). The alarm stops when the last viewer leaves, when the clock is paused, and at full time.

## Check usage
```bash
npx wrangler whoami >/dev/null && python3 -I scripts/cf_usage.py
```
It sums the whole account's usage for today and exits 1 when any limit passes 50%
(`CF_WARN=0.8` to change). It reads wrangler's OAuth token and never prints it.

## Rules
- No Workers Paid, R2, Queues, Containers or new Workers for Absolute Scenes without asking.
- Do not leave a load test or a looping demo script running against the live Worker.
- If usage nears 50% of a limit, pause matches (`POST /api/match/:id/control {"action":"pause"}`).
