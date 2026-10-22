"""Every core analytic runs on simulated frames and gives sane, JSON-safe output."""

import json

from chalktalk_core import analytics as an


def test_analytics_over_sim_frames(match):
    frames = list(match.frames(0, None, 25))
    owned = [f for f in frames if f["ball"]["owner"] and f["ball"]["owner"] != "REF"]
    assert owned
    for f in owned[::4]:
        team = next(p["team"] for p in f["players"] if p["id"] == f["ball"]["owner"])
        results = [
            an.team_shape(f, "home"),
            an.team_shape(f, "away"),
            an.line_gap(f, "away"),
            an.pressure_on_ball(f),
            an.pitch_control(f, team),
            an.offside_line(f, "away" if team == "home" else "home"),
            an.pass_options(f),
            an.shot_xg(f),
        ]
        for r in results:
            json.dumps(r.to_dict())
        assert 0 <= results[3].value <= 1
        assert 0 <= results[4].value <= 1
        assert results[0].value > 0
    window = list(match.frames(0, 500, 1))
    assert an.pressing_intensity(window, "away").evidence_window["end_t"] == window[-1]["t"]
    assert an.ball_speed(window).value > 0
    assert an.player_run(window, "H09").details["distance_m"] > 0
