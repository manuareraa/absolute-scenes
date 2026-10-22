# Stream C: live overlay posting (M5)

The crew POSTs every verified overlay to the edge Worker, which pushes it to the match's viewers
over the `MatchHub` WebSocket. Code: `crew/src/chalktalk_crew/live.py`, wired into the
`run` CLI with `--post`.

## Contract with the Worker (`workers/edge`, stream D)

- `POST {CHALKTALK_EDGE_URL}/api/overlay`, body `{"match_id": ..., "overlay": {...}}`.
- Header `x-chalktalk-secret: $CHALKTALK_OVERLAY_SECRET`. It must equal the Worker's
  `OVERLAY_SECRET`. A wrong secret returns 403; a Worker without one returns 503.
- The Worker only shape-checks. The crew validates against `contracts/schemas/overlay` and
  posts only overlays with `gate.passed`. Bodies are capped at 256 KB, the Worker's limit.
- 429 and 5xx are retried twice with backoff. Any other failure goes into the run log's
  `post_failed`, and the run continues. The overlay stays cached, so re-running with `--post`
  sends it again (cached overlays are replayed, never regenerated).

## Run it against `wrangler dev`

```bash
# once: a local secret for wrangler dev (gitignored)
printf 'OVERLAY_SECRET=%s\n' "$(openssl rand -hex 16)" > workers/edge/.dev.vars
npm --prefix workers/edge run dev          # http://127.0.0.1:8787
# in another shell: the fakes cost $0; add the Azure env for live text and audio
export CHALKTALK_EDGE_URL=http://127.0.0.1:8787
export CHALKTALK_OVERLAY_SECRET="$(sed -n 's/^OVERLAY_SECRET=//p' workers/edge/.dev.vars)"
uv run python -m chalktalk_crew run --half-minutes 3 --max-moments 2 --post
```

The run log lists `posted` and `post_failed` next to `generated` and `cached`.

## Following the live clock (`live`)

`python -m chalktalk_crew live` generates the overlays (or takes them from the cache). It then
joins the match WebSocket (`/ws/match/<id>`) like a viewer and reads the clock `t` from the
`hello`, `frames` and `clock` messages. Each overlay is posted `--ahead-s` (default 8 s) of match
time before its `match_tc`, so the producer console can queue it before the moment airs.

- Before watching, it fetches `/api/match/<id>` once and refuses to run unless the served
  package digest equals the crew's simulated match. That way the moments line up with the clock.
- Moments that aired more than 2 s before the crew joined are logged as `missed`, not posted.
- Joining counts as a viewer, so it starts or resumes the clock as any viewer does. The watch
  ends on `end`, after 30 s with no message (clock paused), or once everything is posted.
- One WebSocket and one POST per overlay; nothing loops against the Worker.

```bash
uv run python -m chalktalk_crew live --half-minutes 5 --max-moments 3 --ahead-s 8
```

The deployed demo match `sim-7` is `--seed 7 --half-minutes 5` with the demo beats
(digest `2b1ac0b4`).

## Result (local `wrangler dev`, 2026-10-22, fakes, $0)

`live --half-minutes 5 --max-moments 3`, with the clock at rate 4 (set through `/control`):

| overlay | moment (ms) | posted at clock t (ms) | ahead |
|---|---|---|---|
| ov-m82120-casual-home-en-GB | 82,120 | 74,462 | 7.7 s |
| ov-m107120-casual-home-en-GB | 107,120 | 102,506 | 4.6 s |
| ov-m187360-casual-home-en-GB | 187,360 | 178,650 | 8.7 s |

Clock batches are 1 s, so at rate 4 the clock advances in 4 s steps; at 1x the lead is within 1 s
of `--ahead-s`. All three POSTs returned 200, and a viewer joining afterwards got them in the
hub's replay. A wrong secret returned 403.
