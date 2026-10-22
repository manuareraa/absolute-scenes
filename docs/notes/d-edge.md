# Stream D: edge live clock (`workers/edge`)

One Worker `chalktalk` on the Cloudflare free plan. Static assets are `workers/edge/public/`,
assembled by `npm run assemble -w workers/edge` from `web/dist` plus match packages:

```bash
uv run python -m chalktalk_sim generate --seed 7 --half-minutes 5 --demo --out ./packages
CHALKTALK_PACKAGES=./packages npm run check:worker   # or: node workers/edge/scripts/assemble.mjs --packages ./packages
```

Each package folder becomes `/matches/<folder>/` (for example `/matches/sim-7/manifest.json`,
`/matches/sim-7/chunks/c00000.json.gz`). Chunks are served as the raw gzip bytes
(no `Content-Encoding`), so the browser gunzips them (`DecompressionStream("gzip")`).

## HTTP
| Route | Who | Does |
|---|---|---|
| `GET /api/health` | anyone | `{ok: true}` |
| `GET /api/match/:id` | web | the package manifest plus `base` (`/matches/:id/`) and `ws` (`/ws/match/:id`). Served from assets; costs no Durable Object request. 404 for an unknown match. |
| `POST /api/overlay` | crew | body `{match_id, overlay}` (overlay per `overlay.schema.json`). Header `x-chalktalk-secret`. Stored (re-posting an id replaces it, last 200 kept) and broadcast. Reply `{ok, id, viewers}`. |
| `POST /api/match/:id/control` | producer / demo script | `{action: "play" \| "pause" \| "reset"}`, `{action: "seek", t}` (match ms), `{action: "rate", rate}` (0.25 to 8). Same secret header. Reply `{ok, clock}`. |

The secret is the Worker secret `OVERLAY_SECRET` (`npx wrangler secret put OVERLAY_SECRET`).
Without it, both POST routes answer 503. The edge does only a light shape check of overlays
(ajv cannot run in Workers), so the crew validates against the contract before posting.

## WebSocket `/ws/match/:id` (server → client only)
| `type` | Fields | When |
|---|---|---|
| `hello` | `viewers, match_id, fps, duration_ms, batch_ms, clock` | on join |
| `overlay` | `overlay` | on join (last 50) and on every crew post |
| `frames` | `t0, t1, clock, frames[], events[]` | every `batch_ms` (1000 ms, so 25 frames) while playing; a first batch on join. `frames` and `events` are the contract documents with `t0 <= t < t1`. |
| `clock` | `clock` | after a control action |
| `end` | `clock` | at the final whistle |

`clock` is `{t, playing, rate, server_ms}`; `t` is match ms at wall time `server_ms`.
Send the text `ping` to get `pong` (answered by the runtime, does not wake the object).
Anything else a client sends is dropped.

## Clock and budget
- The first viewer of a match starts the clock at `t = 0`. When the last viewer leaves, the clock
  pauses and the alarm stops, so an unwatched match spends no requests. It resumes on the next join.
- One alarm per batch while someone watches: 3,600 Durable Object requests per watched hour, well
  under the free 100k a day. Outgoing WebSocket messages are not billed.
- The hub keeps two parsed chunks in memory. Durable Object CPU limit is 30 s per invocation, so the
  once-per-10 s gunzip and parse of a chunk (about 600 kB of JSON) is fine.

## Asks for the coordinator
- Stream A asked for a `hub_message` schema (docs/notes/a-contracts.md). The table above is the
  shape to encode.
