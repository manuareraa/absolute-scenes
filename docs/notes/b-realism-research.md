# B: Match realism research (what makes ChalkTalk's synthetic match read as football)

Date: 2026-10-23. Web research only: nothing was cloned, downloaded or run.
Labels: **[V]** verified from a primary source I read (link given), **[I]** inferred, **[?]** unverified.

## TL;DR

- **Google Research Football (gfootball)** is the only off-the-shelf engine that is licence-clean and fully featured. The Python wrapper is Apache-2.0 [V](https://raw.githubusercontent.com/google-research/football/master/LICENSE). The C++ engine (`third_party/gfootball_engine`, derived from Gameplay Football) is **The Unlicense**, i.e. public domain [V](https://raw.githubusercontent.com/google-research/football/master/third_party/gfootball_engine/LICENSE). It plays real 11v11 with goals, restarts and keepers. The catch: the repo was archived on 2026-08-19 and it has to be built from C++ source. That is a real risk with a 5-day deadline.
- **RoboCup 2D**: rcssserver and librcsc are LGPL-3.0, and helios-base is MIT. This is usable, but it means 23 processes plus C++ builds, so it costs more to integrate than gfootball.
- **Generative trajectory models**: I found no permissively licensed code or weights. They are excluded.
- **Cheapest path**: keep our sim and add (1) formation templates anchored to the ball, separate for in and out of possession, (2) a phase state machine, (3) a scripted goal, celebration and kick-off sequence, and (4) goalkeeper rules. See the ranked list at the end.

---

## 1. Google Research Football (gfootball)

**What it is**: an RL environment from Google Research. It wraps a full 3D football game engine with a C++ core and Python bindings. Its README credits Bastiaan Konings Schuiling, who "authored and open-sourced the original version of this game" [V](https://github.com/google-research/football).

**Licences**
- Python wrapper and repo: Apache License 2.0 [V](https://raw.githubusercontent.com/google-research/football/master/LICENSE).
- C++ engine at `third_party/gfootball_engine/LICENSE`: **The Unlicense**. The file reads "This is free and unencumbered software released into the public domain" [V](https://raw.githubusercontent.com/google-research/football/master/third_party/gfootball_engine/LICENSE). It is **not GPL**, so we can use it.
- Build dependencies are system libraries (SDL2, Boost, etc.), installed with apt [V](https://github.com/google-research/football). We would only link to them while generating data offline and would not ship them, so their licences (zlib and BSL-style) are not a problem [I].
- Engine data and assets (textures, fonts) may carry their own notices. I did not check them [?]. They don't matter if we export only x/y data [I].
- Repo status: "archived by the owner on Aug 19, 2026. It is now read-only" [V](https://github.com/google-research/football). No fixes will come upstream.

**Goals, team shape, restarts**
- Scenarios `11_vs_11_stochastic`, `11_vs_11_easy_stochastic` and `11_vs_11_hard_stochastic` each play a full 90-minute match [V](https://raw.githubusercontent.com/google-research/football/master/gfootball/doc/scenarios.md).
- Game modes in the observation are 0 Normal, 1 KickOff, 2 GoalKick, 3 FreeKick, 4 Corner, 5 ThrowIn and 6 Penalty [V](https://raw.githubusercontent.com/google-research/football/master/gfootball/doc/observation.md). Restarts and kick-offs after goals are built in.
- Action set v2 includes `action_builtin_ai` (ID 19), which lets the game's own AI choose the action [V](https://raw.githubusercontent.com/google-research/football/master/gfootball/doc/observation.md). The opponent team is played by the built-in bot. So sending `builtin_ai` for our side gives AI against AI, and the AI plays in formation with keepers [I].
- Whether built-in AI against built-in AI scores at least 2 goals in a typical match is [?]. We would pick seeds that do, or run several matches and keep good segments [I].

**Output format: can we get x/y per player?** Yes.
- Raw observations include `left_team` and `right_team` (N × [x, y]), `ball` ([x, y, z]), `score` and `game_mode` [V](https://raw.githubusercontent.com/google-research/football/master/gfootball/doc/observation.md).
- Coordinates: x runs from -1 to 1, y from -0.42 to 0.42, and the goal mouth spans y from -0.044 to 0.044 [V](same link).
- Mapping to metres needs **separate x and y scales** (0.84/2 ≠ 68/105). Use x_m = (x+1)·52.5 and y_m = (y+0.42)/0.84·68 [I].
- Episode traces can be dumped as pickles (`dump_full_episodes`) and converted to text with `dump_to_txt.py` [V](https://raw.githubusercontent.com/google-research/football/master/gfootball/doc/saving_replays.md).
- The step rate is not stated in the docs [?]. I believe a 3000-step full match runs at about 10 steps/s of game time. If so, it needs interpolating to our 25 Hz [?]/[I].
- Possession, passes and shots are not reported as events. We would derive them from `ball_owned_team`/`ball_owned_player` changes and `score` deltas [I].

**Integration (Python, 5 days, 14 GB RAM, no GPU)**: medium risk.
- No GPU is needed for the built-in AI, and rendering can be turned off [I].
- PyPI wheel availability and supported Python versions could not be checked because the PyPI page failed to load [?]. If no wheel exists for our Python, we need a source build in a separate venv or container, likely an older Python such as 3.8 or 3.9 [?].
- Run it **offline only**: generate 1 to 3 matches once, convert them to our 25 Hz JSON schema, and commit the JSON. The deployed app never imports gfootball [I].
- Estimate: 0.5 day if it builds first time, but it could take 2+ days if it doesn't [I]. We need a hard time-box: about 4 hours to get a first dumped match, else drop it [I].

## 2. RoboCup Soccer Simulation 2D

| Component | Licence | Usable? |
|---|---|---|
| rcssserver (the simulator) | LGPL-3.0 [V](https://github.com/rcsoccersim/rcssserver) | Yes. Run it unmodified as a separate process; it is not GPL/AGPL [I] |
| librcsc (agent library) | LGPL-3.0 [V](https://github.com/helios-base/librcsc) | Yes, dynamic link, unmodified [I] |
| helios-base (team base code) | MIT, "Copyright (c) 2021 HELIOS Base" [V](https://raw.githubusercontent.com/helios-base/helios-base/master/LICENSE) | Yes |
| agent2d (older HELIOS base on OSDN) | not verified, possibly GPL [?] | **Treat as excluded**; use helios-base, its successor [I] |
| Pyrus2D (Python base team) | MIT per its paper [?](https://arxiv.org/abs/2307.16875) | Yes, but it still needs rcssserver |

- **Goals, restarts and shape**:
  - One cycle is 100 ms, and `half_time` is 300 s [V](https://rcsoccersim.readthedocs.io/en/latest/soccerserver.html).
  - Play modes include `before_kick_off`, `kick_off_*`, `goal_*`, `corner_kick_*`, `goal_kick_*`, `kick_in_*`, `free_kick_*`, `offside_*` and `penalty_kick_*` [V](same link).
  - Base teams play in formations, and goals happen regularly between two base teams [?].
  - The helios-base formation system maps ball position to player positions with Delaunay triangulation (Akiyama & Noda) [?]. That is exactly the idea worth copying in section 5.
- **Output**: `.rcg` game logs hold per-cycle player and ball positions at 10 Hz. They can be played back with rcssmonitor [V](https://github.com/rcsoccersim/rcssserver) (playback) and [?] (exact rcg field layout). We would need to upsample to 25 Hz [I].
- **Integration**: hard for 5 days. It needs C++ builds of rcssserver, librcsc and helios-base, then 22 agent processes plus 2 coaches. Agents are a disc-shaped 2D abstraction with no z for the ball, so the ball is never in the air [I]. RAM is fine [I]. Estimate 1 to 2 days [I].

## 3. Other open football sims and game AIs

- **footballsimulationengine** (Aiden Gallagher): **MIT**, Node.js, 11v11 [V](https://github.com/gallagheraiden/footballsimulationengine).
  - Each iteration returns JSON with the ball `[x,y,z]` and each player's `currentPOS`/`intentPOS`. It also covers goals, shots, corners, fouls, penalties and the half-time side switch [V](same link).
  - It has no formation logic, because we would supply positions ourselves [V](same link: not described).
  - It is usable as a reference or for porting ideas. Running it would need a Node sidecar. Its visual quality is unknown [?].
- **rSoccer** (RobôCIn): **MIT**, but it models small-robot VSS/SSL leagues, not 11v11 football, and full rules are not described [V](https://github.com/robocin/rSoccer). Not relevant.
- **RobotFootballSim**: C++/Box2D robot football [V via search snippet](https://github.com/EgorOrachyov/RobotFootballSim). Licence unverified [?]. Not relevant.
- **Buckland "Simple Soccer"** (*Programming Game AI by Example*, ch. 4): the classic steering plus finite-state-machine football AI. Players hold home "regions" that shift with the attacking or defending state, and a "supporting attacker" uses sweet-spot scoring [?] (book content from memory). Code licence unverified [?], and a JS port exists [?](https://github.com/luiskarlos/soccer). **Copy the design, not the code** [I].
- I found no "Bonsai-style" football sim with a clear licence [?].

## 4. Generative tracking models

| Work | Code | Licence | Weights |
|---|---|---|---|
| JointDiff (ICLR 2026): diffusion over joint multi-agent trajectories plus possession events [V](https://arxiv.org/html/2509.22522v1) | repo has dataset loaders and metrics [V](https://github.com/guillem-cf/JointDiff) | **none stated** [V] | none mentioned [V] |
| MIDAS (ECML-PKDD 2025): trajectory imputation [V](https://github.com/gkswns95/midas) | training code | **none stated** [V] | none [V] |
| TranSPORTmer (ACCV 2024): imputation and forecasting [V](https://openaccess.thecvf.com/content/ACCV2024/html/Capellera_TranSPORTmer_A_Holistic_Approach_to_Trajectory_Understanding_in_Multi-Agent_Sports_ACCV_2024_paper.html) | none found [?] | n/a | n/a |
| SMGDiff (2024): single-player soccer *motion* (body) generation [V](https://arxiv.org/pdf/2411.16216) | not checked [?] | [?] | [?] |
| DeepMind Graph Imputer (2022) | not released [?] | n/a | n/a |

- **Verdict**: no repo states a licence, so default copyright applies. All of them are **excluded** for a commercial-safe entry [I]. Even with weights, training or sampling needs real tracking data and GPU time, which does not fit 5 days [I].
- **Data we *could* use**: the **IDSSE** dataset has 7 Bundesliga matches with official TRACAB tracking and events under **CC-BY 4.0**, crediting the DFL and citing Bassek et al. 2025 [V](https://github.com/spoho-datascience/idsse-data). It is good for *fitting formation templates* (section 5) without shipping real matches. Its sample rate is not stated on the page; TRACAB is typically 25 Hz [?].
- **Metrica sample data** has no formal licence, only "be responsible, acknowledge" [V](https://github.com/metrica-sports/sample-data). **Avoid for anything shipped** [I].

## 5. Analytics-literature approaches to drive a rule-based sim

- **Role-based formations (Bialkowski et al., ICDMW 2014)** [V](https://authors.library.caltech.edu/records/4v1fx-ymm70) and [V](https://la.disneyresearch.com/publication/large-scale-analysis-of-soccer-matches-using-spatiotemporal-tracking-data/):
  - Each frame, players are assigned to *roles* (formation slots), not fixed identities, and the roles are learned by minimum-entropy partitioning.
  - Use in our sim: give each team a role template (e.g. 4-3-3 slot coordinates), and re-assign players to slots with Hungarian assignment when shape breaks. That stops two players stacking on one spot [I].
- **Dynamic formations (Shaw & Glickman, 2019)** [V](https://www.sportperformanceanalysis.com/s/Dynamic-analysis-of-team-strategy-in-professional-football-By-Laurie-Shaw-And-Mark-Glickman.pdf) (via search summary):
  - Formations are measured separately **in possession and out of possession**, as positions *relative to one another*, and clustered with a Wasserstein metric.
  - Use in our sim: keep two templates per team. Attacking is wide and high, with full-backs pushed up into a 2-3-5 look. Defending is compact, a 4-4-2 block about 35 m deep [I].
- **Ball-anchored positioning** (helios-base Delaunay formations [?], Buckland home regions [?]):
  - Each slot's target = team centroid offset + template offset scaled by phase.
  - The centroid follows the ball in x with damping (about 0.5–0.7 of ball x) and in y (about 0.3–0.5).
  - The defensive block's width compresses toward the ball side [I].
  - This single function gives about 80% of "looks like football" [I].
- **Pitch control and EPV** (Spearman 2018 pitch control [?]; Fernández & Bornn EPV [?]):
  - Laurie Shaw's Friends-of-Tracking code is **MIT** and includes `Metrica_PitchControl.py`, `Metrica_EPV.py` and an `EPV_grid.csv` [V](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking).
  - Cheap use: score candidate pass targets by `EPV(target) × P(receiver reaches first)`, using a simple time-to-intercept calculation. Shoot when EPV or xG beats the best pass [I]. That gives build-up that progresses forward instead of randomly.
  - Keep the EPV grid static (a lookup), with no ML. Credit it as MIT [I].
- **Movement physics**: cap speed at about 7–9 m/s sprint and 2–4 m/s jog, cap acceleration at about 3–4 m/s², and turn smoothly with a steering "arrive" behaviour [I]. Without this, motion looks like random objects running about.

## 6. Public "Inside the Game" hackathon entries

- The Reactor event page describes the series as part of the "Inside the Game: Developer Hackathon Series". The 2026-10-14 livestream "Build AI-powered soccer insights apps with AKS and ACA" (Brian Benz) used examples of play styles, counterattacks and player performance [V](https://developer.microsoft.com/en-us/reactor/events/27536/).
- The series page lists that one event, with no links to GitHub, Devpost or YouTube project pages. It says participants turn "synthetic football events" into explainable match intelligence [V](https://developer.microsoft.com/en-us/reactor/series/s-1709/).
- Search snippets mention a scenario called "Synthetic Match Insights Engine for Premier League Studio" and a 2026-10-21 Azure Databases session [?] (snippets only).
- **I found no public submissions** on Devpost, GitHub or YouTube as of 2026-10-23 [V by absence in searches; may simply not be indexed yet].
- The organisers' emphasis is on *insight and explanation* from synthetic **events**, not pixel-real tracking [I]. So realism only needs to be convincing enough to support the narrative, and readable goals matter more than fine-grained physics [I].

---

## Recommendation: cheapest change set, ranked by visual impact per hour

Assumptions: we keep the Python director plus role movement. Hour estimates are [I].

1. **Ball-anchored formation templates, in and out of possession** (about 3 h; highest impact).
   - Use a 4-3-3 attacking template and a 4-4-2 defending template in normalised pitch coordinates.
   - Slot target = `anchor(ball, phase) + template[slot] * (width_scale, depth_scale)`.
   - Shift the defending block toward the ball side.
   - The back line holds a single shared x (the "line"), clamped so it doesn't go past the halfway line when defending deep.
2. **Movement realism: steering "arrive", speed and acceleration caps, look-ahead** (about 2 h).
   - Players ease into targets instead of snapping.
   - The nearest 1–2 defenders press the ball carrier; everyone else holds shape.
   - This removes the "random objects" look on its own.
3. **Scripted goal sequence** (about 3 h; the must-have for "readable goals").
   - Build-up: 3–6 passes that move forward, with targets chosen by an EPV lookup [MIT grid] or simply "most advanced open teammate".
   - Then cutback or through-ball, shot, ball into the net (inside the y-range of the goal mouth, with z under 2.44 m), and the keeper dives the wrong way or too late.
   - **Celebration**: for about 6–8 s, the scorer runs to a corner flag and 3–5 teammates converge on him; the conceding team walks back and the keeper picks the ball out of the net.
   - **Reset**: for about 6 s, both teams walk (under 2 m/s) to kick-off formation in their own halves, the conceding team kicks off from the centre spot, and the event log gets `goal`, `celebration`, `kickoff`.
   - The director schedules 2–3 of these at chosen minutes.
4. **Phase state machine** (about 2 h): `kickoff → build_up → progression → final_third → shot → (goal | save | miss) → restart`.
   - Transitions are driven by ball x, possession and director cues. Each phase sets the template scales: build-up is wide and deep, the final third is high, with full-backs overlapping.
   - Also add turnovers and transitions (counterattack) so possession changes look motivated.
5. **Goalkeeper rules** (about 1.5 h).
   - Stay on the arc between the ball and the goal centre, 2–6 m off the line, further out when the ball is far away.
   - React to shots by moving laterally toward the shot line, capped by reach.
   - Take goal kicks and short distributions to centre-backs who drop wide.
   - Never leave the penalty area except on a rush-out triggered by a through-ball.
6. **Restarts beyond kick-off** (about 2 h): goal kick (keeper at the 6-yard line, centre-backs split), throw-in, and a corner with a box crowd. Each gives another readable set-piece moment.
7. **Optional: fit templates from IDSSE (CC-BY 4.0)** (about 3 h).
   - Compute in- and out-of-possession average relative slot positions by ball zone, and use them as lookup tables.
   - This makes the shape data-grounded and credible to Premier League judges. It needs an attribution line.
8. **Optional: gfootball offline generation** (time-box 4 h).
   - Only if items 1 to 5 are done early. Treat it as a stretch goal or alternative data source, not the main path, given that the repo is archived and must be built from source.

**Excluded**: GPL or unclear agent2d, all generative trajectory models (no licence or weights), and Metrica data (no formal licence).
