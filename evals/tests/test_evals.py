import copy

import pytest
from chalktalk_crew import FakeAnalyticsTools, fake_crew
from chalktalk_evals import (
    Thresholds,
    claim_grounding,
    cue_timing,
    evaluate,
    key_facts_coverage,
    load_moments,
    numeric_tolerance,
    run_suite,
)
from chalktalk_evals.metrics import p95


@pytest.fixture(scope="module")
def tools():
    return FakeAnalyticsTools()


@pytest.fixture(scope="module")
def overlay():
    moment = load_moments()[0]
    return fake_crew().run(moment["events"], lenses=("analyst",))[0]


def test_moments_are_synthetic_and_well_formed():
    moments = load_moments()
    assert len(moments) >= 4
    for m in moments:
        assert m["events"] and m["expect_tools"]
        for e in m["events"]:
            assert e["source"] == "sim"
            assert all(a[0] in "ha" and a[1:].isdigit() for a in e["actors"])


def test_suite_passes_on_fake_crew(tools):
    report = run_suite(fake_crew(), tools)
    assert report["passed"], [r for r in report["rows"] if r["failures"]]
    assert report["summary"]["overlays"] == len(load_moments()) * 9
    assert report["summary"]["grounding_rate"] == 1.0


def test_grounding_catches_unbound_number(overlay):
    ov = copy.deepcopy(overlay)
    assert claim_grounding(ov)["grounding_rate"] == 1.0
    ov["script"]["text"] += " Then 42 more."
    g = claim_grounding(ov)
    assert g["grounding_rate"] < 1.0
    assert g["numbers"] - g["grounded_numbers"] == 1


def test_numeric_tolerance(overlay, tools):
    ov = copy.deepcopy(overlay)
    assert numeric_tolerance(ov, tools)["within_tolerance_rate"] == 1.0
    claim = next(c for c in ov["claims"] if c["tolerance"])
    claim["value"] += claim["tolerance"] * 0.9
    assert numeric_tolerance(ov, tools)["within_tolerance_rate"] == 1.0
    claim["value"] += claim["tolerance"]
    res = numeric_tolerance(ov, tools)
    assert res["within_tolerance_rate"] < 1.0
    assert res["max_abs_error"] > claim["tolerance"]


def test_cue_timing_rule(overlay):
    ov = copy.deepcopy(overlay)
    t = cue_timing(ov)
    assert t["cue_bound_rate"] == 1.0 and t["negative_starts"] == 0
    assert t["cue_word_align_p95_ms"] == 0.0
    cues = {c["cue_id"]: c["offset_ms"] for c in ov["script"]["cues"]}
    s = ov["strokes"][0]
    start = cues[s["cue_id"]] - s["lead_ms"]  # stroke start = offset - lead
    t = cue_timing(ov, {s["id"]: start + 30})
    assert t["sync_median_ms"] == 30.0
    s["lead_ms"] = cues[s["cue_id"]] + 1
    assert cue_timing(ov)["negative_starts"] == 1
    s["cue_id"] = "missing"
    assert cue_timing(ov)["cue_bound_rate"] < 1.0


def test_evaluate_gates_on_thresholds(overlay, tools):
    ok = evaluate([overlay], tools)
    assert ok["passed"]
    sid = overlay["strokes"][0]["id"]
    late = evaluate([overlay], tools, observed_starts={overlay["id"]: {sid: 10_000_000}})
    assert not late["passed"]
    assert late["rows"][0]["failures"] == ["sync_p95_ms"]
    lax = evaluate(
        [overlay],
        tools,
        thresholds=Thresholds(sync_p95_ms=1e9),
        observed_starts={overlay["id"]: {sid: 10_000_000}},
    )
    assert lax["passed"]
    assert not evaluate([], tools)["passed"]


def test_key_facts_coverage(overlay):
    assert key_facts_coverage(overlay, ["line_gap"]) == 1.0
    assert key_facts_coverage(overlay, ["line_gap", "xg"]) == 0.5


def test_p95():
    assert p95([]) == 0.0
    assert p95(list(range(1, 101))) == 95
    assert p95([7.0]) == 7.0
