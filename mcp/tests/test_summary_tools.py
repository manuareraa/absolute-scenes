import json

import pytest
from chalktalk_contracts import validate
from chalktalk_mcp.tools import Tools

MID = "sim-11"


def test_half_time_and_catch_up(store):
    tools = Tools(store)
    h = tools.half_time(MID)
    json.dumps(h)
    assert h["tool_call"]["name"] == "half_time"
    assert h["value"] == "1-0"  # the demo beat's home goal comes before half-time
    moments = h["details"]["moments"]
    assert 1 <= len(moments) <= 3 and [m["t"] for m in moments] == sorted(m["t"] for m in moments)
    goal = next(m for m in moments if m["kind"] == "goal")
    assert goal["rank"] == 1 and goal["var"]["decision"] == "goal_stands"
    for m in moments:
        w = m["evidence_window"]
        assert w["start_t"] <= m["t"] <= w["end_t"] <= h["evidence_window"]["end_t"]
        names = [tc["name"] for tc in m["evidence"]]
        assert names[0] == "events"
        for tc in m["evidence"]:
            validate("claim", {"id": "c", "text_slot": "s", "value": 0, "tool_call": tc,
                               "evidence_window": w, "verified": None})  # fmt: skip
            assert tools.verify(tc["name"], tc["args"], output_hash=tc["output_hash"])["verified"]
    for g in h["geometry"]:
        assert g["geometry_m"]["points"]
    # The Verifier can re-run the summary itself.
    tc = h["tool_call"]
    assert tools.verify("half_time", tc["args"], tc["output_hash"])["verified"]

    before = tools.catch_up(MID, 40_000)  # the scripted goal lands at about 52 s
    assert before["value"] == "0-0" and all(m["t"] <= 40_000 for m in before["details"]["moments"])
    late = tools.catch_up(MID, 89_000, since_t=45_000, n=1)
    assert [m["kind"] for m in late["details"]["moments"]] == ["goal"]
    assert late["details"]["stats"]["home"]["goals"] == 1
    with pytest.raises(ValueError):
        tools.catch_up(MID, 60_000, n=0)
