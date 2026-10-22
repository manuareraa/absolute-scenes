from chalktalk_core import summary as sm


def ev(i, t, type_, team, actors=("H09",), **attrs):
    return {"id": f"e{i:03d}", "t": t, "type": type_, "team": team, "actors": list(actors),
            "attrs": attrs}  # fmt: skip


def shot(i, t, team, xg, outcome, pid="H09", start=(40.0, 5.0)):
    end = [52.5, 1.0, 1.0] if team == "home" else [-52.5, 1.0, 1.0]
    return ev(i, t, "shot", team, (pid,), start=list(start), end=end, xg=xg, outcome=outcome)


EVENTS = [
    ev(0, 0, "kickoff", "home", period=1),
    ev(1, 1000, "pass", "home", start=[0, 0], end=[10, 0], outcome="complete", receiver="H10"),
    ev(2, 5000, "pass", "away", ("A07",), start=[0, 0], end=[-10, 0], outcome="incomplete"),
    shot(3, 10_000, "home", 0.04, "off_target"),
    shot(4, 20_000, "away", 0.45, "saved", "A10", (-45.0, 2.0)),
    shot(5, 30_000, "home", 0.30, "goal"),
    ev(6, 30_400, "goal", "home", score={"home": 1, "away": 0}),
    ev(7, 33_400, "var_check", "home", reason="possible offside"),
    ev(8, 44_400, "var_decision", "home", decision="goal_stands"),
    ev(9, 50_000, "offside", "away", ("A11",), at=[-40.0, 3.0]),
    shot(10, 60_000, "away", 0.50, "goal", "A10", (-44.0, 0.0)),  # cut out: no goal event
    ev(11, 70_000, "foul", "away", ("A04", "H10"), at=[20.0, 10.0]),
    ev(12, 70_500, "card", "away", ("A04",), colour="red"),
    ev(13, 80_000, "period_end", None, (), period=1),
]


def test_moments_rank_goals_then_red_cards_then_chances():
    ms = sm.key_moments(EVENTS, 0, 80_000, n=3)
    assert [m["kind"] for m in ms] == ["chance", "goal", "card"]  # match order
    assert [m["rank"] for m in ms] == [3, 1, 2]
    chance, goal, card = ms
    assert goal["events"] == ["e005", "e006", "e007", "e008"]
    assert goal["var"] == {"check_t": 33_400, "decision": "goal_stands"}
    assert goal["headline"] == "Goal, home: 1-0 (VAR: goal stands)"
    # The evidence runs from the build-up to the VAR decision.
    assert goal["evidence_window"] == {"start_t": 22_400, "end_t": 47_400}
    assert goal["geometry"][0]["shape"] == "arrow"
    assert goal["geometry"][0]["geometry_m"]["points"] == [[40.0, 5.0], [52.5, 1.0]]
    # A save adds weight: the 0.45 saved beats the 0.50 that was cut out in flight.
    assert chance["t"] == 20_000 and chance["headline"] == "Chance, away: xG 0.45, saved"
    cut = next(m for m in sm.candidates(EVENTS, 0, 80_000) if m["t"] == 60_000)
    assert cut["headline"].endswith("blocked")  # logged "goal", but no goal event followed
    assert card["geometry"][0]["geometry_m"]["player_id"] == "A04"


def test_offside_and_small_n():
    one = sm.key_moments(EVENTS, 45_000, 55_000, n=3)
    assert [m["kind"] for m in one] == ["offside"]
    assert one[0]["evidence_window"] == {"start_t": 42_000, "end_t": 53_000}


def test_team_stats():
    st = sm.team_stats(EVENTS, 0, 80_000)
    home, away = st["home"], st["away"]
    assert (home["goals"], home["shots"], home["on_target"]) == (1, 2, 1)
    assert (away["goals"], away["shots"], away["on_target"]) == (0, 2, 1)
    assert home["xg"] == 0.34 and away["xg"] == 0.95
    assert home["pass_accuracy"] == 1.0 and away["pass_accuracy"] == 0.0
    assert away["offsides"] == 1 and away["cards"] == 1
    assert abs(home["possession"] + away["possession"] - 1) < 1e-3


def test_summary_value_and_numbered_geometry():
    r = sm.summary(EVENTS, 0, 80_000, n=3, metric="half_time").to_dict()
    assert r["metric"] == "half_time" and r["value"] == "1-0"
    assert r["evidence_window"] == {"start_t": 0, "end_t": 80_000}
    labels = [g["geometry_m"]["text"] for g in r["geometry"] if g["shape"] == "label"]
    assert labels == ["1", "2", "foul", "3"]  # each moment numbered after its strokes
    assert all(g["geometry_m"]["points"] for g in r["geometry"])
    assert sm.summary(EVENTS, 0, 25_000).value == "0-0"
