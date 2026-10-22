import json

import pytest
from chalktalk_contracts import validate
from chalktalk_mcp.tools import NOT_EVIDENCE, TOOL_NAMES, Tools

MID = "sim-11"
LISTINGS = {"match_info", "frame", "events"}  # data, not numbers to draw


def calls(t):
    return {
        "team_shape": {"match_id": MID, "t": t, "team": "away"},
        "line_gap": {"match_id": MID, "t": t, "team": "away"},
        "distance_between": {"match_id": MID, "t": t, "a": "H09", "b": "A04"},
        "pressure": {"match_id": MID, "t": t},
        "pitch_control": {"match_id": MID, "t": t, "team": "home"},
        "control_at": {"match_id": MID, "t": t, "team": "home", "x": 30, "y": 0},
        "shot_xg": {"match_id": MID, "t": t},
        "offside_line": {"match_id": MID, "t": t, "defending_team": "away"},
        "pass_options": {"match_id": MID, "t": t},
        "formation": {"match_id": MID, "t": t, "team": "away"},
        "obso": {"match_id": MID, "t": t},
        "xt_added": {"match_id": MID, "start_t": t, "end_t": t + 2000},
        "line_breaking_passes": {"match_id": MID, "start_t": 0, "end_t": 90_000, "team": "home"},
        "pressing_intensity": {"match_id": MID, "start_t": 0, "end_t": 60_000, "team": "away"},
        "ball_speed": {"match_id": MID, "start_t": 0, "end_t": 60_000},
        "player_run": {"match_id": MID, "start_t": t, "end_t": t + 4000, "player_id": "H09"},
        "ghost": {"match_id": MID, "player_id": "A04", "start_t": t, "end_t": t + 8000},
    }


def test_every_number_draws_its_evidence(store, owned_t):
    """M9: every tool that returns a number returns strokes to draw and a window to replay."""
    tools = Tools(store)
    cs = calls(owned_t)
    numeric = set(TOOL_NAMES) - set(NOT_EVIDENCE) - LISTINGS
    assert numeric <= set(cs), f"add evidence cases for {sorted(numeric - set(cs))}"
    for name in sorted(numeric):
        out = getattr(tools, name)(**cs[name])
        w = out["evidence_window"]
        assert 0 <= w["start_t"] <= w["end_t"], name
        assert out["geometry"], f"{name} draws nothing"
        for g in out["geometry"]:
            assert g["geometry_m"]["points"], name


def test_evidence_replays_a_claim(store, owned_t):
    tools = Tools(store)
    claim = tools.shot_xg(MID, owned_t)
    tc = claim["tool_call"]
    ev = tools.evidence(tc["name"], tc["args"], output_hash=tc["output_hash"])
    json.dumps(ev)
    d = ev["details"]
    assert ev["value"] == claim["value"] and d["hash_match"] is True
    assert d["claim_tool_call"] == tc
    assert ev["evidence_window"] == claim["evidence_window"]
    assert d["replay"] == {"start_t": owned_t - 2000, "end_t": owned_t + 2000}
    assert all(d["replay"]["start_t"] <= e["t"] <= d["replay"]["end_t"] for e in d["events"])
    assert len(d["ball_path"]) > 1
    assert ev["geometry"][: len(claim["geometry"])] == claim["geometry"]
    assert ev["geometry"][-1]["shape"] == "run"
    validate("claim", {"id": "c", "text_slot": "s", "value": ev["value"],
                       "tool_call": ev["tool_call"], "evidence_window": ev["evidence_window"],
                       "verified": None})  # fmt: skip
    # A stale hash is reported.
    stale = tools.evidence(tc["name"], tc["args"], output_hash="sha256:x")
    assert stale["details"]["hash_match"] is False


def test_evidence_clamps_and_refuses(store):
    tools = Tools(store)
    long = tools.evidence(
        "line_breaking_passes",
        {"match_id": MID, "start_t": 0, "end_t": 90_000, "team": "home"},
        pad_ms=0,
    )
    r = long["details"]["replay"]
    assert r["end_t"] - r["start_t"] <= 60_000 and r["end_t"] == 90_000
    for bad in ("verify", "evidence", "list_matches", "nope"):
        with pytest.raises(ValueError):
            tools.evidence(bad, {})
    with pytest.raises(ValueError):
        tools.evidence("pressure", {"match_id": MID, "t": 0}, pad_ms=-1)
