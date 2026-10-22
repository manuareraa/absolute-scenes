# Stream B: match package format (sim → web, hub, mcp)

Written by `chalktalk_sim.write_package`; generate one with

```bash
uv run python -m chalktalk_sim generate --seed 7 --half-minutes 5 --demo --out ./packages
```

```
<out>/sim-<seed>/
  manifest.json          format, match_id, seed, fps, duration_ms, teams (fictional names,
                         formation, colours, players {id, number, name, role}), referee,
                         score, digest, chunk_ms, chunks[{file, start_t, end_t, frames}],
                         events {file, count}
  events.json            event.schema.json documents, sorted by t, ids e00001…
  chunks/c00000.json.gz  gzip JSON array of frame.schema.json documents (10 s = 250 frames)
```

- Player ids: `H<shirt>` home, `A<shirt>` away, `REF` referee (team `ref`). Index order in
  every frame is stable: home 11, away 11, referee.
- `t` runs on from period 1 kick-off; period 2 starts at `half_minutes * 60000` (no half-time
  frames). Teams swap ends in period 2 (`chalktalk_core.geometry.attack_sign`).
- Frames always carry `body_heading` (facing the ball; the carrier faces travel).
- Event `attrs` by type: `pass {start, end, length_m, height: ground|high, receiver, outcome:
  complete|incomplete|offside|out, restart?}`, `shot {start, end:[x,y,z], xg, speed_ms,
  outcome: goal|saved|off_target}`, `carry {start, end, length_m}`, `press {distance_m}`
  (actors: presser, carrier), `goal {score}`, `var_check {reason}`, `var_decision {decision}`,
  restarts `{at}`.
- Output is byte-identical for the same seed and config (gzip mtime is 0).

No contract change is needed. If the web prefers a columnar chunk (smaller), stream B can add
`format: 2` alongside; ask in the shared notes.
