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

## Result (local, 2026-10-22)

See the PR description for the run log of the local test.
