# Stream B: IDSSE credit for docs/data-credits.md (coordinator path)

`docs/data-credits.md` says the full IDSSE citation is added by stream B with the loader.
That file is a coordinator path, so please replace the IDSSE bullet's "full citation" line
with:

- Bassek, M., Rein, R., Weber, H. and Memmert, D. (2025). *An integrated dataset of
  spatiotemporal and event data in elite soccer.* Scientific Data.
  https://doi.org/10.1038/s41597-025-04505-y. Dataset: figshare,
  https://doi.org/10.6084/m9.figshare.28196177.v1. Licence: CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). Data © DFL Deutsche Fußball Liga.
- Changes: we read two matches' positions and events
  (`sim/src/chalktalk_sim/calibrate.py`) and keep only quantile summaries of speed,
  acceleration, team length and width, pressure distance, pass length and ball speed
  (`sim/src/chalktalk_sim/data/reference_profile.json`), plus five fitted kinematic numbers.
  No positions, events, names or ids are committed, shipped or shown.
