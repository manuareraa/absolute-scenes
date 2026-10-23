"""The demo match reads as football: scripted goals, a celebration, a walk back, a kick-off."""

import numpy as np
import pytest
from chalktalk_core.geometry import FRAME_MS
from chalktalk_sim import MatchConfig, simulate
from chalktalk_sim.director import DEMO_BEATS
from chalktalk_sim.match import BOWNER, BX, BY, PX, PY


@pytest.fixture(scope="module")
def demo():
    return simulate(MatchConfig(seed=7, half_minutes=5, beats=DEMO_BEATS))


def of(m, kind):
    return [e for e in m.events if e["type"] == kind]


def test_the_script_is_the_score(demo):
    goals = of(demo, "goal")
    assert [g["team"] for g in goals] == ["home", "away", "home"]
    assert [g["attrs"]["score"] for g in goals] == [
        {"home": 1, "away": 0},
        {"home": 1, "away": 1},
        {"home": 2, "away": 1},
    ]
    assert demo.meta["score"] == goals[-1]["attrs"]["score"]
    # Each goal lands within a minute of its beat and follows a shot marked "goal".
    beats = [b.t_ms for b in DEMO_BEATS if b.kind == "goal"]
    for g, bt in zip(goals, beats, strict=True):
        assert bt <= g["t"] <= bt + 60_000
    shots = [s for s in of(demo, "shot") if s["attrs"]["outcome"] == "goal"]
    assert len(shots) == len(goals)
    for s, g in zip(shots, goals, strict=True):
        assert s["actors"] == g["actors"] and 0 < g["t"] - s["t"] < 3000
    # The first goal goes to VAR and the decision comes before the restart.
    var = of(demo, "var_decision")
    assert len(var) == 1 and goals[0]["t"] < var[0]["t"] < of(demo, "kickoff")[1]["t"]


def test_celebration_walk_back_and_kickoff(demo):
    idx = {p.id: i for i, p in enumerate(demo.lineup)}
    kickoffs = [k["t"] for k in of(demo, "kickoff")]
    for g in of(demo, "goal"):
        f0 = g["t"] // FRAME_MS
        sc = idx[g["actors"][0]]
        team = [i for i, p in enumerate(demo.lineup) if p.team == g["team"] and p.role != "GK"]
        mates = [i for i in team if i != sc]
        # Eight seconds on, the scorer is out wide with team-mates piled round him.
        f = f0 + 8000 // FRAME_MS
        scorer = demo.players[f, sc, [PX, PY]]
        assert abs(scorer[1]) > 15.0
        d = np.linalg.norm(demo.players[f, mates][:, [PX, PY]] - scorer, axis=1)
        assert np.sum(d < 8.0) >= 5
        # The ball is played back to the centre spot, never teleported.
        nxt = min(k for k in kickoffs if k > g["t"])
        f1 = nxt // FRAME_MS
        path = demo.ball[f0:f1, [BX, BY]]
        assert np.max(np.linalg.norm(np.diff(path, axis=0), axis=1)) < 1.0
        assert np.linalg.norm(path[-1]) < 0.5
        assert 15_000 <= nxt - g["t"] <= 40_000


def test_keeper_holds_after_a_save(demo):
    idx = {p.id: i for i, p in enumerate(demo.lineup)}
    saves = of(demo, "save")
    assert saves
    for sv in saves:
        gk = idx[sv["actors"][0]]
        f0 = sv["t"] // FRAME_MS + 1
        held = demo.ball[f0 : f0 + 50, BOWNER] == gk
        assert held.all()  # two seconds in hand
        moved = np.linalg.norm(demo.players[f0 + 49, gk, [PX, PY]] - demo.players[f0, gk, [PX, PY]])
        assert moved < 1.5
