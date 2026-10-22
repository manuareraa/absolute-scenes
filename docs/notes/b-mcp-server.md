# B: Analyst MCP server (`mcp/`)

Python MCP server (`mcp` SDK 2.x, MIT) with the Analyst's deterministic tools.

## Run
- stdio: `uv run python -m chalktalk_mcp`
- HTTP: `uv run python -m chalktalk_mcp --transport streamable-http --port 8000`
  - Endpoint `/mcp` is stateless with JSON responses; health is `GET /healthz`.
- Docker, from the repo root: `docker build -f mcp/Dockerfile -t chalktalk-mcp .`
  - Image is about 330 MB, runs as non-root and listens on `:8000`.
  - `mcp/Dockerfile.dockerignore` keeps the build context small.

## Env
| var | default | meaning |
|---|---|---|
| `CHALKTALK_PACKAGES` | unset | Directory of match packages (`<dir>/sim-<seed>/manifest.json`, as written by `python -m chalktalk_sim generate`). Tools read frames from these packages. |
| `CHALKTALK_SIM_HALF_MINUTES` | 45 | For a `sim-<seed>` with no package, the match is regenerated with the demo beats and this half length. |
| `CHALKTALK_MAX_MATCHES` | 2 | Generated matches kept in memory. A full 90-minute match is about 65 MB. |
| `HOST` / `PORT` | 127.0.0.1 / 8000 | The image sets `0.0.0.0`. |

**Make sure the browser and the tools see the same match.** Either point `CHALKTALK_PACKAGES` at the same packages the Worker serves, or generate with the same seed and settings. The manifest now records `half_minutes`, `periods`, `beats` and `calibration`, and `chalktalk_sim.config_from_meta` rebuilds the match exactly: the digest matches.

## Tools
Every tool except `list_matches` and `verify` returns:
- `match_id`, `metric`, `value`, `unit`, `evidence_window {start_t, end_t}`
- `geometry`: a list of `{shape, geometry_m: {points, radius?, player_id?, text?}}`, plus `style.variant` on pass lanes. Shapes come from the overlay stroke vocabulary. The crew adds stroke ids and cue ids.
- `details`
- `tool_call {id, name, args, output_hash}`: copy it as-is into `claim.tool_call`.

`output_hash` is `sha256:` over the canonical JSON (sorted keys, floats rounded to 4 decimal places) of the output without `tool_call`.

| tool | args | value |
|---|---|---|
| list_matches | | |
| match_info | match_id | teams, players, score, duration |
| frame | match_id, t | the contract frame |
| events | match_id, start_t?, end_t?, types?, team? | count (max 200 listed) |
| team_shape | match_id, t, team | outfield hull m², plus width, length, lines, gaps |
| line_gap | match_id, t, team, between=defence_midfield\|midfield_attack | m |
| distance_between | match_id, t, a, b | m |
| pressure | match_id, t | P(opponent reaches the carrier within 1.5 s) |
| pitch_control | match_id, t, team, zone?=[x0,y0,x1,y1], include_grid? | share |
| control_at | match_id, t, team, x, y | prob |
| shot_xg | match_id, t, player_id? | xG |
| offside_line | match_id, t, defending_team | line x (m), attackers beyond it |
| var_offside | match_id, t, player_id? | VAR check of the last pass (15 s): margin (m, > 0 offside), decision, line, pass lane |
| pass_options | match_id, t | number of safe options; each with lane risk, control, xT gain, offside |
| formation | match_id, t, team, window_s?=30 | formation (4-4-2, 4-3-3, 4-2-3-1, 4-5-1, 3-5-2, 3-4-3, 5-3-2) from the average shape over the window; roles, lines and slots per player |
| obso | match_id, t, team? | off-ball scoring opportunity (xG of the next action), with the 3 most dangerous cells as zones |
| xt_added | match_id, start_t, end_t | ΔxT of the ball move, for the team in possession at start_t |
| line_breaking_passes | match_id, start_t, end_t, team | completed passes that break opponent lines; lines broken and opponents bypassed per pass |
| pressing_intensity | match_id, start_t, end_t, team | mean pressure on the opponent's carrier (window ≤ 180 s) |
| ball_speed | match_id, start_t, end_t | top speed in m/s (km/h in details) |
| player_run | match_id, start_t, end_t, player_id | top speed in m/s; path, distance |
| ghost | match_id, player_id, start_t, end_t (≤ 30 s), baseline_s?=60 | gap (m) between the real player and the ghost at the end. Geometry: `ghost_path` (last point = expected position, `player_id` = real player), the real `run`, a `ring` at the ghost. Details: `deltas` of pitch control, net OBSO and pressing (ghost − real, from the player's team's view) |
| verify | name, args, output_hash?, value?, tolerance? | `{verified, hash_match, value_ok, value, diff}` |
| evidence | name, args, output_hash?, pad_ms=2000 | M9 tap-a-number: re-runs the call; its value, strokes and window, plus a replay window (padded, max 60 s), the events in it, the ball path (dashed `run`) and `hash_match` |

Errors (unknown match, t outside the match, unknown player, bad zone) come back as MCP tool errors with a plain message.

## For stream D (deploy)
**Azure request** (stream B creates nothing in Azure; the credit is $100 in total):
- Image: GHCR (`ghcr.io/<owner>/chalktalk-mcp`), built by CI from `mcp/Dockerfile`. No ACR.
- One Container App, workload profile **Consumption** only, `minReplicas: 0`, `maxReplicas: 1`, 0.5 vCPU / 1 GiB, in the shared Container Apps environment.
- Monthly cost, approximate: **$0** for demo use. Example: 20 active hours is 36,000 vCPU-s and 72,000 GiB-s, inside the free grant of 180,000 vCPU-s and 360,000 GiB-s per subscription each month.
  - Worst case, if it is kept awake around the clock: about $35 a month. That is why it needs `minReplicas: 0`.
- Logs: give the environment's Log Analytics workspace a daily cap, or send logs nowhere. Ingestion is the one cost that grows on its own.

- Container Apps settings:
  - target port 8000, scale to zero
  - liveness probe on `/healthz`
  - about 0.5 vCPU / 1 GiB is enough with `CHALKTALK_MAX_MATCHES=2`
- **The server has no auth.** Use internal ingress (the crew calls it from inside the environment), or put it behind an API key or Easy Auth at the ingress. Do not expose it publicly as is.
- Packages: either bake them into a derived image or mount them, and set `CHALKTALK_PACKAGES`. Otherwise matches are regenerated on first use, which takes about 25 s for 2×45 minutes. Pre-warm by calling `match_info` once.
