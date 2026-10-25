"""Shots and goals obey physical limits (docs/notes/b-believable-goals.md)."""

import numpy as np
import pytest
from chalktalk_core.geometry import FRAME_MS, HALF_LENGTH, attack_sign
from chalktalk_sim import MatchConfig, simulate
from chalktalk_sim.director import DEMO_BEATS
from chalktalk_sim.match import BX, BY, BZ, PX, PY

DT = FRAME_MS / 1000


@pytest.fixture(scope="module", params=["demo7", "seed1"])
def game(request):
    if request.param == "demo7":
        return simulate(MatchConfig(seed=7, half_minutes=5, beats=DEMO_BEATS))
    return simulate(MatchConfig(seed=1, half_minutes=15))


def shots(m):
    return [e for e in m.events if e["type"] == "shot"]


def keeper(m, team):
    return next(i for i, p in enumerate(m.lineup) if p.team == team and p.role == "GK")


def other(team):
    return "away" if team == "home" else "home"


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


def test_shots_come_from_shooting_range(game):
    for s in shots(game):
        t = s["t"] // FRAME_MS
        goal = np.array([attack_sign(s["team"], int(game.period[t])) * HALF_LENGTH, 0.0])
        assert np.linalg.norm(np.array(s["attrs"]["start"]) - goal) <= 32.5


def test_keeper_is_between_ball_and_goal_at_every_shot(game):
    for s in shots(game):
        t = s["t"] // FRAME_MS
        goal = np.array([attack_sign(s["team"], int(game.period[t])) * HALF_LENGTH, 0.0])
        gk = game.players[t, keeper(game, other(s["team"])), [PX, PY]]
        assert seg_dist(gk, np.array(s["attrs"]["start"]), goal) < 2.0, s["t"]


def test_no_player_moves_faster_than_10_ms(game):
    same = game.period[1:] == game.period[:-1]
    p = game.players[:, :22, :][:, :, [PX, PY]].astype(np.float64)
    speed = np.linalg.norm(np.diff(p, axis=0), axis=2)[same] / DT
    assert speed.max() <= 10.0


def flight(m, s):
    """Ball frames from the strike to the goal, save or block (at most 3 s)."""
    t0 = s["t"] // FRAME_MS
    t1 = t0 + int(3000 / FRAME_MS)
    for e in m.events:
        if e["t"] > s["t"] and e["type"] in ("goal", "save", "ball_out"):
            t1 = min(t1, e["t"] // FRAME_MS)
            break
    return t0, t1


def test_goals_go_past_defenders_and_keeper(game):
    goals = [s for s in shots(game) if s["attrs"]["outcome"] == "goal"]
    for s in goals:
        dfn = other(s["team"])
        gk = keeper(game, dfn)
        outfield = [i for i, p in enumerate(game.lineup) if p.team == dfn and i != gk]
        t0, t1 = flight(game, s)
        for i in range(t0 + 2, t1 + 1):
            b = game.ball[i, [BX, BY]]
            low = game.ball[i, BZ] < 1.9
            if low:
                d = np.linalg.norm(game.players[i, outfield][:, [PX, PY]] - b, axis=1)
                assert d.min() >= 0.5, (s["t"], i)
            if game.ball[i, BZ] < 2.4:
                assert np.linalg.norm(game.players[i, gk, [PX, PY]] - b) >= 1.0, (s["t"], i)


def test_blocked_shots_name_the_blocker(game):
    for s in shots(game):
        if s["attrs"]["outcome"] == "blocked":
            assert s["attrs"]["blocked_by"] in {p.id for p in game.lineup}
