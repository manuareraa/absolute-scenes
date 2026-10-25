"""The live-ask eval's question set and scoring, on recorded events (no Azure)."""

import json

from chalktalk_evals.ask_live import FIXTURE, build_questions, judge_rows, summarize


def test_question_set_covers_moments_views_languages_and_attacks():
    qs = build_questions(json.loads(FIXTURE.read_text(encoding="utf-8")))
    normal = [q for q in qs if q["kind"] == "normal"]
    assert len(normal) >= 60
    assert {q["lang"] for q in normal} == {"en-GB", "es-ES"}
    assert {q["lens"] for q in normal} == {"analyst", "casual", "newcomer"}
    assert len({q["match_tc"] for q in normal}) >= 10
    assert sum(q["kind"] == "attack" for q in qs) == 6
    assert len({q["id"] for q in qs}) == len(qs)


def _q(kind="normal", qid="q000"):
    return {"id": qid, "kind": kind, "question": "What happened here?", "match_tc": 1000}


TOOL = {"name": "pitch_control", "args": {"t": 1000}, "summary": "0.61"}
CF = {"proposal": "p", "accepted": True, "metrics": []}
OVERLAY = {
    "type": "overlay",
    "t_ms": 12000,
    "overlay": {
        "gate": {"passed": True},
        "script": {"text": "Pitch control was 61%."},
        "claims": [{"value": 0.61, "unit": "share", "tool_call": {"name": "pitch_control"}}],
    },
}


def test_summary_counts_gates_rejections_counterfactuals_and_refusals():
    runs = [
        {"q": _q(), "events": [
            {"type": "tool", "tool": TOOL},
            {"type": "verdict", "verdict": {"ok": False, "round": 1}},
            {"type": "verdict", "verdict": {"ok": True, "round": 2}},
            {"type": "counterfactual", "counterfactual": CF},
            OVERLAY,
        ]},
        {"q": _q(qid="q001"), "events": [{"type": "refusal"}]},
        {"q": _q("attack", "a00"), "events": [{"type": "refusal"}]},
    ]  # fmt: skip
    s = summarize(runs)
    assert s["questions"] == 2 and s["answered_with_overlay"] == 1 and s["gate_passed"] == 1
    assert s["refused_normal"] == 1 and s["attacks_refused"] == 1 and s["attacks_answered"] == 0
    assert (s["verifier_round1_claims"], s["verifier_round1_rejected"]) == (1, 1)
    assert s["verifier_rejected_after_rewrite"] == 0
    assert (s["counterfactuals"], s["counterfactuals_accepted"]) == (1, 1)
    assert s["overlay_ready_s"]["median"] == 12.0

    rows = judge_rows(runs)
    assert [r["id"] for r in rows] == ["q000"]
    assert rows[0]["response"] == "Pitch control was 61%."
    assert "pitch_control" in rows[0]["context"] and "accepted" in rows[0]["context"]
