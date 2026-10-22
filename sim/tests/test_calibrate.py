"""The DFL loader on a tiny made-up match in the same XML layout (no real data)."""

import json

import numpy as np
import pytest
from chalktalk_sim import calibrate

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<PutDataRequest>\n'
TEAMS = {"home": "T-H", "away": "T-A"}
FRAMES = 200
STARTS = {"firstHalf": 10000, "secondHalf": 100000}


def pid(side, i):
    return f"P-{side[0].upper()}{i:02d}"


def write_match(d):
    d.mkdir()
    info = [HEAD, "<MatchInformation><Teams>"]
    for side, tid in TEAMS.items():
        info.append(f'<Team TeamId="{tid}" Role="{"home" if side == "home" else "guest"}">')
        info.append("<Players>")
        for i in range(11):
            pos = "TW" if i == 0 else "ZD"
            info.append(f'<Player PersonId="{pid(side, i)}" PlayingPosition="{pos}" />')
        info.append("</Players></Team>")
    info.append("</Teams></MatchInformation></PutDataRequest>\n")
    (d / "a.xml").write_text("".join(info))

    ev = [HEAD]
    plays = [(10.0, 20.0, "P-H05", "P-H06"), (30.0, 20.0, "P-H06", None)]
    for x, y, player, recv in plays:
        r = f' Recipient="{recv}" Evaluation="successfullyCompleted"' if recv else ""
        ev.append(f'<Event X-Position="{x}" Y-Position="{y}"><Play Player="{player}"{r}>')
        ev.append("<Pass /></Play></Event>\n")
    ev.append("</PutDataRequest>\n")
    (d / "b.xml").write_text("".join(ev))

    pos = [HEAD, '<Positions><MetaData Type="pitch-size"><PitchSize X="105" Y="68"/></MetaData>']
    for section, n0 in STARTS.items():
        for side, tid in TEAMS.items():
            sign = -1 if side == "home" else 1
            for i in range(11):
                attrs = f'GameSection="{section}" TeamId="{tid}" PersonId="{pid(side, i)}"'
                pos.append(f"<FrameSet {attrs}>")
                for k in range(FRAMES):
                    x = sign * (5 + 4 * i) + 0.2 * k
                    y = -30 + 6 * i
                    pos.append(f'<Frame N="{n0 + k}" X="{x:.2f}" Y="{y:.2f}" S="18.00" />')
                pos.append("</FrameSet>")
        pos.append(f'<FrameSet GameSection="{section}" TeamId="BALL" PersonId="B">')
        for k in range(FRAMES):
            # Ball at the feet of home player 5 (x = -25 + 0.2 k, y = 0).
            x = -25 + 0.2 * k
            pos.append(
                f'<Frame N="{n0 + k}" X="{x:.2f}" Y="0.5" S="18.00" BallStatus="1" '
                'BallPossession="1" />'
            )
        pos.append("</FrameSet>")
    pos.append("</Positions></PutDataRequest>\n")
    (d / "c.xml").write_text("".join(pos))
    return d


def test_find_and_load(tmp_path):
    d = write_match(tmp_path / "m1")
    files = calibrate.find_files(d)
    assert {k: v.name for k, v in files.items()} == {
        "info": "a.xml",
        "events": "b.xml",
        "positions": "c.xml",
    }
    m = calibrate.load_match(d)
    assert len(m.people) == 22
    assert [s.period for s in m.sections] == [1, 2]
    sec = m.sections[0]
    assert sec.xy.shape == (FRAMES, 22, 2)
    assert np.allclose(sec.speed, 5.0)  # 18 km/h
    assert m.pass_lengths.tolist() == pytest.approx([20.0])
    team = np.array([p.team for p in m.people])
    own = calibrate.owners(sec, team)
    assert (own == [p.pid for p in m.people].index("P-H05")).all()


def test_samples_and_build(tmp_path):
    d = write_match(tmp_path / "m1")
    m = calibrate.load_match(d)
    s = calibrate.match_samples(m)
    assert np.allclose(s["speed_ms"], 5.0)
    assert np.allclose(s["team_width_m"], 54.0)  # outfield y from -24 to 30
    assert np.allclose(s["team_length_m"], 36.0)
    assert len(s["pressure_distance_m"]) > 0
    out = tmp_path / "ref.json"
    assert calibrate.main([str(d), "--out", str(out)]) == 0
    ref = json.loads(out.read_text())
    assert ref["matches"] == 1
    assert ref["profile"]["speed_ms"]["q"][50] == 5.0


def test_missing_file(tmp_path):
    d = write_match(tmp_path / "m1")
    (d / "c.xml").unlink()
    with pytest.raises(FileNotFoundError):
        calibrate.find_files(d)
