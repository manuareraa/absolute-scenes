import numpy as np
import pytest
from chalktalk_contracts import validate
from chalktalk_vision.events import arc_at_line, ballistic_fit, compare, detect
from chalktalk_vision.pitch_tracks import PitchFrame, pick_balls

CAM = np.array([0.0, -62.0, 22.0])
DT = 0.04


def ground_of(b):
    """Where the camera ray through a 3D ball point meets the ground."""
    b = np.asarray(b, float)
    return CAM[:2] + (b[:2] - CAM[:2]) * CAM[2] / (CAM[2] - b[2])


def test_ballistic_fit_recovers_a_lofted_kick():
    s, v = np.array([30.0, 5.7, 0.0]), np.array([25.0, -4.5, 6.5])
    t = np.arange(1, 16) * DT
    b = s + v * t[:, None] - np.outer(t**2 / 2, [0, 0, 9.81])
    g = np.array([ground_of(p) for p in b])
    start, vel = ballistic_fit(g, t, s[:2], CAM)
    assert start == pytest.approx(s, abs=0.05)
    assert vel == pytest.approx(v, abs=0.1)
    tt, y, z = arc_at_line(start, vel, 52.5)
    assert tt == pytest.approx(0.9, abs=0.01)
    assert abs(y) < 3.66 and 0 < z < 2.44


def _scenario():
    """Home attacks +x: a carry, a pass, a shot that scores, then the kickoff reset."""
    frames = []
    gks = [
        {"id": 1, "team": "home", "cls": "goalkeeper", "x": -50.0, "y": 0.0},
        {"id": 20, "team": "away", "cls": "goalkeeper", "x": 51.0, "y": 8.0},
    ]

    def add(ball, p1, p2):
        people = [dict(g) for g in gks]
        people.append({"id": 2, "team": "home", "cls": "player", "x": p1[0], "y": p1[1]})
        people.append({"id": 3, "team": "home", "cls": "player", "x": p2[0], "y": p2[1]})
        people.append({"id": 30, "team": "away", "cls": "player", "x": 10.0, "y": 15.0})
        fb = (
            None
            if ball is None
            else {"x": float(ball[0]), "y": float(ball[1]), "box": [0, 0, 1, 1]}
        )
        frames.append(PitchFrame(len(frames), (0, 0, 27), 0.0, [], people, fb))

    for k in range(20):  # carry 0 -> 5 m
        x = 5.0 * k / 19
        add((x + 0.3, 0.0), (x, 0.0), (15.0, 0.0))
    for k in range(1, 26):  # ground pass at 10 m/s
        add((5.3 + 10 * k * DT, 0.0), (5.0, 0.0), (15.0, 0.0))
    for _ in range(10):  # receiver holds
        add((15.3, 0.0), (5.0, 0.0), (15.0, 0.0))
    s, v = np.array([15.3, 0.0, 0.0]), np.array([25.0, -0.5, 8.0])
    k = 1
    while True:  # shot until it crosses the goal line
        t = k * DT
        b = s + v * t - np.array([0, 0, 9.81 * t * t / 2])
        if b[0] > 52.5:
            break
        add(ground_of(b), (15.0, 0.0), (15.5, 1.0))
        k += 1
    for _ in range(5):  # not seen inside the net, then reset to the centre spot
        add(None, (16.0, 0.0), (16.0, 1.0))
    for _ in range(10):
        add((0.0, 0.0), (16.0, 0.0), (16.0, 1.0))
    return frames


def test_detect_finds_carry_pass_shot_goal():
    frames = _scenario()
    ev = detect(frames, start_ms=60_000, camera_position=tuple(CAM))
    kinds = [e["type"] for e in ev]
    for want in ("carry", "pass", "shot", "goal"):
        assert want in kinds, kinds
    assert "ball_out" not in kinds
    for e in ev:
        assert e["source"] == "video" and 0 <= e["confidence"] <= 1
        validate("event", e)
    pas = next(e for e in ev if e["type"] == "pass")
    assert pas["actors"] == ["T2", "T3"] and pas["team"] == "home"
    assert pas["t"] == pytest.approx(60_000 + 19 * 40, abs=80)
    shot = next(e for e in ev if e["type"] == "shot")
    assert shot["attrs"]["outcome"] == "goal"


def test_compare_counts_matches_within_tolerance():
    sim = [
        {"id": "e1", "t": 1000, "type": "pass", "actors": ["H02", "H03"]},
        {"id": "e2", "t": 5000, "type": "shot", "actors": ["H03"]},
    ]
    video = [
        {"id": "v1", "t": 1200, "type": "pass", "actors": ["T2", "T3"], "confidence": 0.8},
        {"id": "v2", "t": 9000, "type": "shot", "actors": ["T3"], "confidence": 0.8},
    ]
    r = compare(video, sim, {2: "H02", 3: "H03"})
    assert r["matched"] == 1 and r["precision"] == 0.5 and r["recall"] == 0.5
    assert r["timing_mae_ms"] == 200 and r["actor_accuracy"] == 1.0


def test_pick_balls_ignores_weak_far_candidates():
    def c(x, y, s):
        return {"box": [x - 4, y - 8, x + 4, y], "score": s}

    tracks = [
        {"balls": [c(500, 300, 0.6), c(900, 400, 0.2)]},
        {"balls": [c(510, 300, 0.25), c(900, 400, 0.3)]},  # weak but close wins
        {"balls": [c(900, 400, 0.25)]},  # penalty-spot style false positive alone
        {"balls": []},
        {"balls": [c(540, 302, 0.2)]},  # ball back within the gate
    ]
    picks = pick_balls(tracks, 1280)
    xs = [None if p is None else p["box"][0] + 4 for p in picks]
    assert xs == [500, 510, None, None, 540]
