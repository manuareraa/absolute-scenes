# Stream C → Stream B: analyst tool names and output shape

The crew (`crew/`) calls tools through `chalktalk_crew.tools.ToolClient.call(name, args) -> dict`.
Until the MCP server lands it runs against `FakeAnalyticsTools`, stubbed on these names from
the build plan (§2.2 "Analyst tools"). Please confirm or rename; the crew adapts in one table
(`chalktalk_crew.analyst.TOOL_SPECS`).

## Tools the crew calls in M1
| Tool | Args | `value` / `unit` | `geometry` (pitch metres, origin centre) |
|---|---|---|---|
| `line_gap` | `t`, `team` (defending) | gap between midfield and back line, `m` | `points`: 2 points across the gap |
| `pass_options` | `t`, `team`, `player?` | forward pass options, `options` | `points`: best lane, start → end |
| `pitch_control` | `t`, `team` | share of a zone the team controls, `%` | `points`: zone polygon |
| `pressing_intensity` | `t`, `team`, `player?` | pressers within tackling range, `players` | `player_id` + `radius` |
| `offside_line` | `t`, `team` (defending) | line x from halfway, `m` | `points`: the line, touchline to touchline |
| `shape_compactness` | `t`, `team` | defensive block area, `m2` | `points`: block polygon |
| `xg` | `t`, `team`, `player?` | shot xG, `xG` | `points`: shot origin → goal centre |

`t` is match ms (the play being explained), `team` is `home`/`away`, `player` is a sim player id.

## Output shape requested
```json
{"value": 11.4, "unit": "m", "geometry": {"points": [[10.2, -4.0], [31.5, 6.8]]},
 "provenance": {"tool": "line_gap", "...": "..."}}
```
- `geometry` uses the overlay `Geometry` fields (`points`, `radius`, `player_id`, `text`) so the
  crew copies it straight into `strokes[].geometry_m`, untouched.
- **Deterministic**: the same `(name, args)` must give the same output (the Verifier re-runs the
  tool and compares within tolerance, and compares the sha256 of canonical JSON).
- Tolerances the Verifier uses: `line_gap` 0.5 m, `pitch_control` 2 %, `offside_line` 0.2 m,
  `shape_compactness` 10 m², `xg` 0.01, counts exact.

## Transport
For M1 a plain Python callable is enough (`ToolClient` protocol). For M4 the crew will need the
MCP endpoint URL from an env var (`CHALKTALK_MCP_URL`); no keys in code.
