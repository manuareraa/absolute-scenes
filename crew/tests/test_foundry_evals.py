"""S4 evaluators: the Foundry dataset (10 items) scores locally in CI, and each evaluator fails
the defect it exists for."""

import copy
import sys
from pathlib import Path

import pytest
from chalktalk_crew import FakeAnalyticsTools, fake_crew

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals" / "src"))

from chalktalk_evals import (  # noqa: E402
    ClaimGroundednessEvaluator,
    CueTimingEvaluator,
    NumericToleranceEvaluator,
    build_items,
    evaluate_local,
)
from chalktalk_evals.foundry import judge_cost_usd, write_jsonl  # noqa: E402
from chalktalk_evals.metrics import NUMBER  # noqa: E402


@pytest.fixture(scope="module")
def rows():
    tools = FakeAnalyticsTools()
    return build_items(fake_crew(), tools, 10)


def test_ten_items_pass_every_evaluator(rows, tmp_path):
    assert len(rows) == 10 and len({r["id"] for r in rows}) == 10
    report = evaluate_local(rows)
    assert report["passed"], [r for r in report["rows"] if r["failed"]]
    assert set(report["metrics"].values()) == {1.0}
    lines = write_jsonl(rows, tmp_path / "d.jsonl").read_text().splitlines()
    assert len(lines) == 10


def test_items_cover_every_lens_and_side(rows):
    assert {r["overlay"]["lens"] for r in rows} == {"casual", "analyst", "newcomer"}
    assert {r["overlay"]["side"] for r in rows} == {"home", "away", "neutral"}


def _first_number(row):
    return next(iter(NUMBER.findall(row["overlay"]["script"]["text"])))


def test_groundedness_fails_a_spoken_number_no_claim_made(rows):
    row = copy.deepcopy(next(r for r in rows if NUMBER.search(r["overlay"]["script"]["text"])))
    text = row["overlay"]["script"]["text"]
    row["overlay"]["script"]["text"] = text.replace(_first_number(row), "99", 1)
    out = ClaimGroundednessEvaluator()(**{k: row[k] for k in ("overlay", "tool_outputs")})
    assert out["claim_groundedness_result"] == "fail" and out["unsupported_numbers"] >= 1


def test_groundedness_fails_a_claim_without_its_tool_output(rows):
    row = copy.deepcopy(rows[0])
    out = ClaimGroundednessEvaluator()(overlay=row["overlay"], tool_outputs={})
    assert out["claim_groundedness_result"] == "fail" and out["claims_backed_by_tool"] == 0.0


def test_tolerance_fails_a_value_off_the_tool_output(rows):
    row = copy.deepcopy(rows[0])
    for out in row["tool_outputs"].values():
        out["value"] = out["value"] * 3 + 10
    out = NumericToleranceEvaluator()(overlay=row["overlay"], tool_outputs=row["tool_outputs"])
    assert out["numeric_tolerance_result"] == "fail" and out["max_abs_error"] > 0
    missing = NumericToleranceEvaluator()(overlay=row["overlay"], tool_outputs={})
    assert missing["numeric_tolerance_result"] == "fail"


def test_cue_timing_fails_a_cue_off_its_word(rows):
    row = copy.deepcopy(rows[0])
    cue = row["overlay"]["script"]["cues"][0]
    starts = sorted(w["offset_ms"] for w in row["overlay"]["script"]["words"])
    gaps = [(b - a, a) for a, b in zip(starts, starts[1:], strict=False)]
    gap, at = max(gaps)
    assert gap > 120
    cue["offset_ms"] = at + gap // 2
    out = CueTimingEvaluator()(overlay=row["overlay"])
    assert out["cue_timing_result"] == "fail" and out["cue_word_align_p95_ms"] > 50


def test_cue_timing_fails_an_unbound_stroke(rows):
    row = copy.deepcopy(rows[0])
    row["overlay"]["strokes"][0]["cue_id"] = "nope"
    assert CueTimingEvaluator()(overlay=row["overlay"])["cue_timing_result"] == "fail"


def test_judge_cost_is_cents():
    assert 0 < judge_cost_usd(10) < 0.02


def test_groundedness_reads_numbers_in_the_overlay_language(rows):
    row = copy.deepcopy(next(r for r in rows if "." in "".join(NUMBER.findall(
        r["overlay"]["script"]["text"]))))  # fmt: skip
    ov, ev = row["overlay"], ClaimGroundednessEvaluator()
    ov["lang"] = "es-ES"
    assert ev(overlay=ov, tool_outputs=row["tool_outputs"])["claim_groundedness_result"] == "fail"
    ov["script"]["text"] = NUMBER.sub(lambda m: m[0].replace(".", ","), ov["script"]["text"])
    assert ev(overlay=ov, tool_outputs=row["tool_outputs"])["claim_groundedness_result"] == "pass"
