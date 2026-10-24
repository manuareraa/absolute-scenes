# Data and asset credits

ChalkTalk's matches, clubs and players are synthetic and fictional. No real match footage, club names, crests or league marks are used.

## Calibration only (not shipped or shown)
- **IDSSE dataset** (Bassek et al., 2025). Official tracking and event data from seven matches. Licence: CC-BY 4.0. Data © DFL Deutsche Fußball Liga.
  - We use it only to fit the distributions of our generator (speed, acceleration, line spacing, pass length) and to benchmark its realism.
  - The full citation is added by stream B with the loader.
- **Wyscout open event data** (Pappalardo, L., Cintia, P., Rossi, A., Massucco, E., Ferragina, P., Pedreschi, D. and Giannotti, F. (2019). *A public data set of spatio-temporal match events in soccer competitions.* Scientific Data 6, 236. https://doi.org/10.1038/s41597-019-0247-7). Dataset: figshare, events article 7770599. Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
  - Changes: we fitted a three-coefficient logistic xG model (distance and goal angle) on the open-play shots from the England, Germany and Spain 2017/18 event files.
  - Only the coefficients are in `core/src/chalktalk_core/analytics.py`. No events, names or ids are committed, shipped or shown.

## Assets
- Player figures are drawn procedurally in code; no third-party models are used.
