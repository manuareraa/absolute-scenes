import json

import pytest
from chalktalk_contracts import validate
from chalktalk_core.analytics import FORMATIONS
from chalktalk_mcp.store import PackageSource, Store, UnknownMatch
from chalktalk_mcp.tools import TOOL_NAMES, Tools
from chalktalk_sim import write_package

MID = "sim-11"


def claim_for(out, slot="v"):
    return {
        "id": "c1",
        "text_slot": slot,
        "value": out["value"],
        "unit": out["unit"],
        "tool_call": out["tool_call"],
        "evidence_window": out["evidence_window"],
        "tolerance": 0.01,
        "verified": None,
    }


def all_calls(t):
    return [
        ("match_info", {"match_id": MID}),
        ("frame", {"match_id": MID, "t": t}),
        ("events", {"match_id": MID, "types": ["pass"], "team": "home"}),
        ("team_shape", {"match_id": MID, "t": t, "team": "away"}),
        ("line_gap", {"match_id": MID, "t": t, "team": "away"}),
        ("distance_between", {"match_id": MID, "t": t, "a": "H09", "b": "A04"}),
        ("pressure", {"match_id": MID, "t": t}),
        ("pitch_control", {"match_id": MID, "t": t, "team": "home", "zone": [0, -34, 52.5, 34]}),
        ("control_at", {"match_id": MID, "t": t, "team": "home", "x": 30, "y": 0}),
        ("shot_xg", {"match_id": MID, "t": t}),
        ("offside_line", {"match_id": MID, "t": t, "defending_team": "away"}),
        ("var_offside", {"match_id": MID, "t": t, "player_id": "H09"}),
        ("pass_options", {"match_id": MID, "t": t}),
        ("formation", {"match_id": MID, "t": t, "team": "away"}),
        ("obso", {"match_id": MID, "t": t}),
        ("xt_added", {"match_id": MID, "start_t": t, "end_t": t + 2000}),
        ("line_breaking_passes", {"match_id": MID, "start_t": 0, "end_t": 90_000, "team": "home"}),
        ("pressing_intensity", {"match_id": MID, "start_t": 0, "end_t": 60_000, "team": "away"}),
        ("ball_speed", {"match_id": MID, "start_t": 0, "end_t": 60_000}),
        ("player_run", {"match_id": MID, "start_t": t, "end_t": t + 4000, "player_id": "H09"}),
        ("ghost", {"match_id": MID, "player_id": "H04", "start_t": t, "end_t": t + 6000}),
    ]


def test_every_tool_returns_a_valid_claim_binding(store, owned_t):
    tools = Tools(store)
    names = set()
    for name, args in all_calls(owned_t):
        out = getattr(tools, name)(**args)
        json.dumps(out)
        names.add(name)
        tc = out["tool_call"]
        assert tc["name"] == name and tc["output_hash"].startswith("sha256:")
        if "value" in out:
            validate("claim", claim_for(out))
            for g in out.get("geometry", []):
                assert g["geometry_m"]["points"]
    assert names | {"list_matches", "verify", "evidence"} == set(TOOL_NAMES)


def test_outputs_are_deterministic_and_verifiable(store, owned_t):
    tools = Tools(store)
    a = tools.pressure(MID, owned_t)
    b = tools.pressure(MID, owned_t)
    assert a == b
    assert tools.pressure(MID, owned_t + 4000)["tool_call"]["id"] != a["tool_call"]["id"]
    tc = a["tool_call"]
    ok = tools.verify(tc["name"], tc["args"], output_hash=tc["output_hash"])
    assert ok["verified"] and ok["hash_match"]
    near = tools.verify(tc["name"], tc["args"], value=a["value"] + 0.005, tolerance=0.01)
    assert near["verified"] and not near["hash_match"]
    far = tools.verify(tc["name"], tc["args"], value=a["value"] + 0.5, tolerance=0.01)
    assert not far["verified"]
    with pytest.raises(ValueError):
        tools.verify("verify", {})


def test_errors(store):
    tools = Tools(store)
    with pytest.raises(UnknownMatch):
        tools.match_info("chelsea")
    with pytest.raises(ValueError):
        tools.frame(MID, 10**9)
    with pytest.raises(ValueError):
        tools.ball_speed(MID, 0, 400_000)
    with pytest.raises(KeyError):
        tools.distance_between(MID, 1000, "H01", "Z99")


def test_package_source_matches_sim(tmp_path, match, owned_t):
    write_package(match, tmp_path)
    from_pkg = Tools(Store(packages=tmp_path))
    from_sim = Tools(Store(packages=tmp_path, prefer_packages=False))
    a = from_pkg.team_shape(MID, owned_t, "home")
    b = from_sim.team_shape(MID, owned_t, "home")
    assert a == b
    assert isinstance(from_pkg.store.get(MID), PackageSource)
    assert from_pkg.list_matches()["matches"][0]["source"] == "package"
    ev = from_pkg.events(MID, types=["pass", "shot"])
    assert ev["value"] > 0
    assert ev == from_sim.events(MID, types=["pass", "shot"])


def test_window_thinning(store):
    src = store.get(MID)
    frames = src.window(0, 60_000, max_frames=100)
    assert len(frames) <= 101
    assert frames[0]["t"] == 0 and frames[-1]["t"] == 60_000


def test_store_lru(match):
    s = Store(packages=None, max_matches=1, half_minutes=0.2)
    s.put(match)
    s.get("sim-3")
    assert [m["match_id"] for m in s.list()] == ["sim-3"]


def test_new_analyst_tools(store, owned_t):
    tools = Tools(store)
    f = tools.formation(MID, owned_t, "home")
    assert f["value"] in FORMATIONS and len(f["details"]["roles"]) == 10
    lb = tools.line_breaking_passes(MID, 0, 90_000, "home")
    assert lb["details"]["completed_passes"] >= lb["value"] >= 0
    o = tools.obso(MID, owned_t)
    assert o["details"]["team"] == "home" and 0 <= o["value"] < 1
    tc = o["tool_call"]
    assert tools.verify(tc["name"], tc["args"], output_hash=tc["output_hash"])["verified"]


def test_ghost_tool(store, owned_t):
    tools = Tools(store)
    out = tools.ghost(MID, "A04", owned_t, owned_t + 8000)
    assert out["unit"] == "m" and out["value"] >= 0
    assert out["geometry"][0]["shape"] == "ghost_path"
    assert set(out["details"]["deltas"]) == {"pitch_control", "obso", "pressing"}
    tc = out["tool_call"]
    assert tools.verify(tc["name"], tc["args"], output_hash=tc["output_hash"])["verified"]
    with pytest.raises(ValueError):
        tools.ghost(MID, "A04", 0, 40_000)


def test_var_offside_agrees_with_the_sim(store):
    tools = Tools(store)
    evs = store.get(MID).events()
    check = next(e for e in evs if e["type"] == "var_check")
    out = tools.var_offside(MID, check["t"])
    # The director's VAR beat ends in "goal stands": the last pass to the scorer's side was onside.
    assert out["details"]["decision"] == "onside" and out["value"] <= 0
    assert out["details"]["attacking_team"] == check["team"]
    assert out["evidence_window"]["end_t"] == check["t"]
    validate("claim", claim_for(out))
    for e in evs:
        if e["type"] == "pass" and e["attrs"].get("outcome") == "offside":
            o = tools.var_offside(MID, e["t"], e["attrs"]["receiver"])
            assert o["details"]["pass_event"] == e["id"]
            assert o["details"]["decision"] == "offside" and o["value"] > 0
    with pytest.raises(ValueError):
        tools.var_offside(MID, -1)  # no pass before kick-off and no player named
