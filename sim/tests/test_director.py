import numpy as np
from chalktalk_contracts import validate
from chalktalk_core.geometry import FRAME_MS
from chalktalk_sim import MatchConfig, simulate
from chalktalk_sim.match import PV, PX, PY

TEAMS = {"home", "away", "ref"}


def test_same_seed_same_match():
    a = simulate(MatchConfig(seed=3, half_minutes=0.5))
    b = simulate(MatchConfig(seed=3, half_minutes=0.5))
    assert a.digest() == b.digest()
    assert a.events == b.events


def test_different_seed_different_match():
    a = simulate(MatchConfig(seed=3, half_minutes=0.5))
    b = simulate(MatchConfig(seed=4, half_minutes=0.5))
    assert a.digest() != b.digest()


def test_frames_follow_contract(match):
    assert match.n_frames == 2 * 150 * 25
    for i in range(0, match.n_frames, 37):
        frame = match.frame(i)
        validate("frame", frame)
        assert frame["t"] == i * FRAME_MS
        assert len(frame["players"]) == 23
        assert {p["team"] for p in frame["players"]} == TEAMS


def test_events_follow_contract(match):
    ids = [e["id"] for e in match.events]
    assert len(ids) == len(set(ids))
    ts = [e["t"] for e in match.events]
    assert ts == sorted(ts)
    for ev in match.events:
        validate("event", ev)
        assert ev["source"] == "sim" and ev["confidence"] == 1.0


def test_event_mix(match):
    types = {e["type"] for e in match.events}
    assert {"kickoff", "pass", "carry", "press", "period_end"} <= types
    passes = [e for e in match.events if e["type"] == "pass"]
    assert len(passes) > 30
    outcomes = {e["attrs"]["outcome"] for e in passes}
    assert outcomes <= {"complete", "incomplete", "offside", "out"}
    done = sum(e["attrs"]["outcome"] == "complete" for e in passes) / len(passes)
    assert 0.6 < done < 0.97
    assert sum(e["type"] == "period_end" for e in match.events) == 2


def test_scripted_goal_and_var(match):
    goals = [e for e in match.events if e["type"] == "goal"]
    assert any(g["team"] == "home" and g["t"] >= 30_000 for g in goals)
    var = [e["type"] for e in match.events if e["type"].startswith("var_")]
    assert var == ["var_check", "var_decision"]
    assert match.meta["score"]["home"] >= 1


def test_player_kinematics_within_limits(match):
    cal = match.meta["calibration"]
    p = match.players
    assert p[:, :22, PV].max() <= 10.0 + 1e-3
    same = match.period[1:] == match.period[:-1]
    dv = np.abs(np.diff(p[:, :, PV], axis=0))[same] / (FRAME_MS / 1000)
    assert dv.max() <= max(cal["accel_max"], cal["decel_max"]) + 0.05
    step = np.hypot(np.diff(p[:, :, PX], axis=0), np.diff(p[:, :, PY], axis=0))[same]
    # One kick-off may move the taker onto the spot; otherwise no jumps.
    assert np.mean(step > 0.5) < 1e-4


def test_shape_is_plausible(match):
    p = match.players
    home = slice(1, 11)
    width = p[::25, home, PY].max(axis=1) - p[::25, home, PY].min(axis=1)
    length = p[::25, home, PX].max(axis=1) - p[::25, home, PX].min(axis=1)
    assert 25 < np.median(width) < 60
    assert 20 < np.median(length) < 55
