# Stream B: sim realism against IDSSE

**Reference data:** two IDSSE matches (Bassek et al. 2025, CC BY 4.0, data by DFL). They are read with `python -I -m chalktalk_sim.calibrate` from a directory outside the repository.
- Only quantile summaries are committed, in `sim/src/chalktalk_sim/data/reference_profile.json` (9 KB, 101 quantiles per metric).
- No positions, events, names or ids are committed.
- The data is used for calibration and benchmarking only. It is never shipped or shown.

**Sim runs:** two full demo matches (seeds 7 and 8, 2 × 45 min). Both sides go through the same `realism.samples_from_arrays`, so the metrics are computed the same way.

KS is the Kolmogorov–Smirnov distance between the sim and reference distributions, averaged over the two seeds. 0 means identical.

| metric | ref median | sim median (old → new) | KS old | KS new |
|---|---|---|---|---|
| accel_ms2 | 0.00 | 0.02 → 0.00 | 0.321 | 0.119 |
| ball_speed_ms | 6.53 | 6.20 → 5.52 | 0.147 | 0.145 |
| pass_length_m | 16.58 | 18.30 → 18.50 | 0.150 | 0.147 |
| pressure_distance_m | 4.28 | 2.84 → 3.21 | 0.222 | 0.184 |
| speed_ms | 1.42 | 2.51 → 1.58 | 0.308 | 0.099 |
| team_length_m | 32.41 | 27.62 → 32.34 | 0.326 | 0.226 |
| team_width_m | 36.69 | 42.75 → 37.53 | 0.319 | 0.144 |
| **mean** | | | **0.256** | **0.152** |

## What changed in `Calibration`
| field | old | new | why |
|---|---|---|---|
| vmax_mean | 8.4 | 7.8 | Fitted: per-player p99.9 speed is 7.81 ± 0.54 m/s. |
| vmax_sd | 0.45 | 0.54 | Fitted. |
| accel_max | 3.6 | 2.5 | The sim applies its cap every tick, so a lower cap matches the real spread better. Real p99.9 peaks are about 6.2 m/s² (accel) and 6.9 m/s² (decel), but they are rare. |
| decel_max | 5.5 | 3.5 | Same reason as accel_max. |
| arrive_gain (new) | 0.9 | 0.35 | Players closed on their slot too hard. This was the main cause of excess speed and acceleration. |
| jog_speed_frac | 0.55 | 0.4 | |
| wander_m | 2.2 | 1.2 | |
| wander_tau_s | 6 | 10 | |
| line_gap_m | 13 | 17 | Teams were too short: median length 27.6 m against 32.4 m. |
| compact_depth | 0.78 | 0.8 | |
| width_scale_in | 1.0 | 0.92 | Teams were too wide: median width 42.8 m against 36.7 m. |
| width_scale_out | 0.72 | 0.55 | Same reason as width_scale_in. |
| press_radius_m | 3.0 | 2.5 | |

## Known gaps
- **Team length** spreads wider in real play (p10 19.5 m to p90 44 m) than in the sim.
- **Pressure distance** is shorter in the sim than in real play.
- **Ball speed** is a little low: real long balls reach about 16 m/s at p90.
- **Real pass lengths** only cover completed passes, measured from the pass to the recipient's next action.
- **The real owner** is the nearest player of the team in possession, within 2 m of the ball.

## Reproduce
```
uv run python -I -m chalktalk_sim.calibrate <idsse>/J03WMX <idsse>/J03WN1 --out /tmp/ref.json
```
This takes 26 s and peaks at 190 MB of memory for two matches, because the 400 MB positions XML is streamed. The regression test is `sim/tests/test_package_realism.py::test_sim_close_to_reference`.
