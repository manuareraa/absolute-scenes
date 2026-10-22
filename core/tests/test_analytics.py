import json

import pytest
from chalktalk_core import analytics as an
from chalktalk_core.provenance import output_hash

STROKE_SHAPES = {
    "arrow", "run", "pass_lane", "line", "offside_line", "zone", "ring", "spotlight",
    "ghost_path", "label",
}  # fmt: skip

# Home attacks +x in period 1. 4-4-2 blocks, home in possession at the halfway line.
HOME = [
    ("H01", -48, 0),
    ("H02", -30, -25), ("H03", -32, -8), ("H04", -32, 8), ("H05", -30, 25),
    ("H06", -12, -20), ("H07", -14, -5), ("H08", 0, 0), ("H09", -12, 20),
    ("H10", 14, -6), ("H11", 16, 7),
]  # fmt: skip
AWAY = [
    ("A01", 49, 0),
    ("A02", 22, -22), ("A03", 20, -7), ("A04", 20, 7), ("A05", 22, 22),
    ("A06", 8, -18), ("A07", 6, -6), ("A08", 6, 6), ("A09", 8, 18),
    ("A10", -4, -3), ("A11", -3, 6),
]  # fmt: skip


def frame(t=1000, owner="H08", moves=None, ball=(0.4, 0.0), ball_v=0.0):
    moves = moves or {}
    players = []
    for team, rows in (("home", HOME), ("away", AWAY)):
        for pid, x, y in rows:
            x, y = moves.get(pid, (x, y))
            players.append({"id": pid, "team": team, "x": x, "y": y, "v": 0.0, "heading": 0.0})
    players.append({"id": "REF", "team": "ref", "x": 5, "y": 10, "v": 0.0, "heading": 0.0})
    return {
        "t": t,
        "period": 1,
        "ball": {"x": ball[0], "y": ball[1], "z": 0.0, "v": ball_v, "owner": owner},
        "players": players,
    }


def check(result):
    d = result.to_dict()
    json.dumps(d)
    assert d["evidence_window"]["start_t"] <= d["evidence_window"]["end_t"]
    for g in d["geometry"]:
        assert g["shape"] in STROKE_SHAPES
        assert g["geometry_m"]["points"]
    assert output_hash(d) == output_hash(result.to_dict())
    return d


def test_team_shape_lines_and_area():
    r = an.team_shape(frame(), "home")
    d = check(r)
    lp = d["details"]["line_players"]
    assert sorted(lp["defence"]) == ["H02", "H03", "H04", "H05"]
    assert sorted(lp["attack"]) == ["H10", "H11"]
    assert d["details"]["width_m"] == 50.0
    assert d["details"]["length_m"] == 48.0
    assert 1000 < d["value"] < 50 * 48


def test_line_gap_grows_when_midfield_pushes_up():
    base = an.line_gap(frame(), "home").value
    pushed = an.line_gap(
        frame(moves={"H06": (-2, -20), "H07": (-4, -5), "H09": (-2, 20)}), "home"
    ).value
    assert pushed > base + 5
    with pytest.raises(ValueError):
        an.line_gap(frame(), "home", between="keeper_defence")


def test_pressure_rises_as_opponent_closes():
    far = an.pressure_on_ball(frame()).value
    near = an.pressure_on_ball(frame(moves={"A11": (1.5, 0.5)})).value
    assert 0 <= far < near <= 1
    d = check(an.pressure_on_ball(frame(moves={"A11": (1.5, 0.5)})))
    assert d["details"]["pressers"][0]["id"] == "A11"
    assert an.pressure_on_ball(frame(owner=None)).value == 0.0


def test_pressing_intensity_window():
    frames = [frame(t=1000 + 40 * i, moves={"A11": (3 - 0.1 * i, 0.5)}) for i in range(10)]
    r = an.pressing_intensity(frames, "away")
    d = check(r)
    assert d["evidence_window"] == {"start_t": 1000, "end_t": 1360}
    assert d["details"]["peak_t"] == 1360
    assert an.pressing_intensity(frames, "home").value == 0.0


def test_pitch_control_halves():
    f = frame()
    home_own = an.pitch_control(f, "home", zone=[-52.5, -34, 0, 34]).value
    away_own = an.pitch_control(f, "away", zone=[0, -34, 52.5, 34]).value
    assert home_own > 0.6 and away_own > 0.6
    whole = an.pitch_control(f, "home").value + an.pitch_control(f, "away").value
    assert whole == pytest.approx(1.0, abs=0.002)
    g = an.pitch_control(f, "home", zone=[-10, -10, 10, 10], include_grid=True)
    assert len(g.details["grid"]["p"]) == 10
    check(an.control_at(f, "home", -30, 0))


def test_xg_and_xt_shape():
    assert an.xg(41.5, 0, 1) > an.xg(30, 0, 1) > an.xg(30, 25, 1)
    assert an.xg(-41.5, 0, -1) == pytest.approx(an.xg(41.5, 0, 1))
    assert an.xt(45, 0, 1) > an.xt(20, 0, 1) > an.xt(-20, 0, 1)
    r = an.xt_added("home", 1, (0, 0), (35, 5))
    assert r.value > 0
    assert an.xt_added("home", 2, (0, 0), (35, 5)).value < 0
    d = check(an.shot_xg(frame(moves={"H08": (40, 2)})))
    assert d["details"]["distance_m"] == pytest.approx(12.66, abs=0.01)


def test_offside_line_and_attackers_beyond():
    f = frame(moves={"H10": (23, -6)})
    d = check(an.offside_line(f, "away"))
    assert d["value"] == 22.0
    assert d["geometry"][0]["shape"] == "offside_line"
    assert d["details"]["attackers_beyond"] == ["H10"]
    assert an.offside_line(frame(), "home").value == -32.0
    # Never in the attackers' own half: away's line pushed past halfway is clamped to 0.
    high = {p: (-5 - i, y) for i, (p, _, y) in enumerate(AWAY)}
    assert an.offside_line(frame(moves=high, ball=(-20, 0)), "away").value == 0.0


def test_pass_options():
    d = check(an.pass_options(frame()))
    ids = {o["id"] for o in d["details"]["options"]}
    assert "H01" not in ids  # 48 m away
    assert d["value"] >= 1
    risks = [o["risk"] for o in d["details"]["options"]]
    assert risks == sorted(risks)
    with pytest.raises(ValueError):
        an.pass_options(frame(owner=None))


def test_ball_speed_and_player_run():
    frames = [frame(t=40 * i, ball_v=float(i)) for i in range(5)]
    d = check(an.ball_speed(frames))
    assert d["value"] == 4.0 and d["details"]["t"] == 160
    run = [frame(t=40 * i, moves={"H10": (14 + 0.3 * i, -6)}) for i in range(5)]
    for i, f in enumerate(run):
        f["players"][9]["v"] = 7.5 if i == 3 else 7.0
    d = check(an.player_run(run, "H10"))
    assert d["value"] == 7.5
    assert d["details"]["distance_m"] == pytest.approx(1.2)
    with pytest.raises(KeyError):
        an.player_run(run, "H99")


def test_distance_between():
    assert an.distance_between(frame(), "H08", "A11").value == pytest.approx(6.71, abs=0.01)
