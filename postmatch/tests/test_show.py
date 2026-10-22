import copy
from datetime import UTC, datetime

import pytest
from chalktalk_contracts import is_valid
from chalktalk_contracts.models.show_schema import Show
from chalktalk_postmatch import build_show, build_shows, chapter_title, match_minute


def overlay(
    i,
    match_tc,
    *,
    side="home",
    lens="casual",
    lang="en-GB",
    tool="line_gap",
    passed=True,
    audio=None,
):
    script = {"text": "Look at the gap.", "cues": [{"cue_id": "k1", "offset_ms": 300}]}
    if audio:
        script["audio_url"] = audio
    return {
        "id": f"ov{i}",
        "stream_tc": 1234,
        "match_tc": match_tc,
        "surface": "broadcast",
        "claims": [
            {
                "id": "c1",
                "text_slot": "x",
                "value": 1.0,
                "unit": "m",
                "tool_call": {"id": "tc1", "name": tool, "args": {}, "output_hash": "sha256:0"},
                "evidence_window": {"start_t": 0, "end_t": match_tc},
                "tolerance": 0.5,
                "verified": passed,
            }
        ],
        "strokes": [
            {
                "id": "s1",
                "shape": "line",
                "geometry_m": {"points": [[0, 0], [1, 1]]},
                "cue_id": "k1",
            }
        ],
        "script": script,
        "lens": lens,
        "side": side,
        "lang": lang,
        "approval": {"state": "approved"},
        "gate": {"passed": passed},
    }


def test_build_show_orders_and_titles():
    ovs = [overlay(2, 3_504_000, tool="xg", audio="r2://a.mp3"), overlay(1, 605_600)]
    show = build_show(
        ovs,
        match_id="sim-001",
        side="home",
        lens="casual",
        lang="en-GB",
        created_at=datetime(2026, 10, 22, 12, tzinfo=UTC),
    )
    assert is_valid("show", show)
    Show.model_validate(show)
    titles = [s["chapter_title"] for s in show["segments"]]
    assert titles == ["11' · The gap between the lines", "59' · The chance"]
    assert show["segments"][1]["audio_url"] == "r2://a.mp3"
    assert all(s["overlay"]["surface"] == "show" for s in show["segments"])
    assert all(s["overlay"]["stream_tc"] is None for s in show["segments"])
    assert show["id"] == "show-sim-001-home-casual-en-GB"
    assert ovs[0]["surface"] == "broadcast"  # inputs untouched


def test_gate_failures_left_out():
    show = build_show(
        [overlay(1, 1000), overlay(2, 2000, passed=False)],
        match_id="m",
        side="home",
        lens="casual",
        lang="en-GB",
    )
    assert [s["overlay"]["id"] for s in show["segments"]] == ["ov1"]
    with pytest.raises(ValueError, match="gate"):
        build_show(
            [overlay(2, 2000, passed=False)], match_id="m", side="home", lens="casual", lang="en-GB"
        )
    show = build_show(
        [overlay(2, 2000, passed=False)],
        match_id="m",
        side="home",
        lens="casual",
        lang="en-GB",
        require_gate=False,
    )
    assert len(show["segments"]) == 1


def test_mixed_batch_rejected():
    with pytest.raises(ValueError, match="not home/casual"):
        build_show(
            [overlay(1, 0, side="away")], match_id="m", side="home", lens="casual", lang="en-GB"
        )


def test_naive_created_at_rejected():
    with pytest.raises(ValueError):
        build_show(
            [overlay(1, 0)],
            match_id="m",
            side="home",
            lens="casual",
            lang="en-GB",
            created_at=datetime(2026, 10, 22),
        )


def test_build_shows_fans_out_per_group():
    ovs = [
        overlay(1, 1000),
        overlay(2, 2000, lens="analyst"),
        overlay(3, 3000, side="away"),
        overlay(4, 4000, side="neutral", passed=False),
    ]
    shows = build_shows(ovs, match_id="m")
    assert [(s["side"], s["lens"]) for s in shows] == [
        ("away", "casual"),
        ("home", "analyst"),
        ("home", "casual"),
    ]


def test_chapter_title_helpers():
    assert match_minute(0) == 1 and match_minute(59_999) == 1 and match_minute(60_000) == 2
    ov = copy.deepcopy(overlay(1, 0, tool="unknown"))
    assert chapter_title(ov) == "1' · The breakdown"
    ov["claims"] = []
    assert chapter_title(ov) == "1' · The breakdown"


def test_shows_from_fake_crew():
    crew_mod = pytest.importorskip("chalktalk_crew")
    events = [
        {
            "id": "e1",
            "t": 600_000,
            "type": "pass",
            "team": "home",
            "actors": ["h4"],
            "source": "sim",
            "confidence": 1.0,
        },
        {
            "id": "e2",
            "t": 601_000,
            "type": "foul",
            "team": "away",
            "actors": ["a6"],
            "source": "sim",
            "confidence": 1.0,
        },
    ]
    ovs = crew_mod.fake_crew().run(events, lenses=crew_mod.LENSES, sides=crew_mod.SIDES)
    shows = build_shows(ovs, match_id="sim-001")
    assert len(shows) == 9
    assert all(is_valid("show", s) for s in shows)
