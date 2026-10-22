"""Eval harness: run the crew over test moments x lenses x sides, score, gate on thresholds."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .metrics import Tools, claim_grounding, cue_timing, key_facts_coverage, numeric_tolerance

MOMENTS_DIR = Path(__file__).resolve().parents[2] / "moments"


@dataclass(frozen=True)
class Thresholds:
    grounding_rate: float = 1.0  # no unsupported number on air
    within_tolerance_rate: float = 1.0
    cue_bound_rate: float = 1.0
    negative_starts: float = 0.0
    cue_word_align_p95_ms: float = 50.0
    sync_p95_ms: float = 100.0  # only when observed starts are supplied (S1 pass bar)
    key_facts_coverage: float = 1.0


def load_moments(directory: Path = MOMENTS_DIR) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))]


def score_overlay(
    overlay: dict[str, Any],
    tools: Tools,
    *,
    expected_tools: list[str] | None = None,
    observed_starts: dict[str, int] | None = None,
) -> dict[str, float]:
    scores = {
        **claim_grounding(overlay),
        **numeric_tolerance(overlay, tools),
        **cue_timing(overlay, observed_starts),
    }
    if expected_tools is not None:
        scores["key_facts_coverage"] = key_facts_coverage(overlay, expected_tools)
    return scores


def failures(scores: dict[str, float], t: Thresholds) -> list[str]:
    checks = [
        ("grounding_rate", scores["grounding_rate"] >= t.grounding_rate),
        ("within_tolerance_rate", scores["within_tolerance_rate"] >= t.within_tolerance_rate),
        ("cue_bound_rate", scores["cue_bound_rate"] >= t.cue_bound_rate),
        ("negative_starts", scores["negative_starts"] <= t.negative_starts),
        ("cue_word_align_p95_ms", scores["cue_word_align_p95_ms"] <= t.cue_word_align_p95_ms),
        ("sync_p95_ms", scores.get("sync_p95_ms", 0.0) <= t.sync_p95_ms),
        ("key_facts_coverage", scores.get("key_facts_coverage", 1.0) >= t.key_facts_coverage),
    ]
    return [name for name, ok in checks if not ok]


def evaluate(
    overlays: list[dict[str, Any]],
    tools: Tools,
    *,
    thresholds: Thresholds | None = None,
    expected_tools: dict[str, list[str]] | None = None,
    observed_starts: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Score each overlay. ``expected_tools`` and ``observed_starts`` are keyed by overlay id."""
    t = thresholds or Thresholds()
    rows = []
    for ov in overlays:
        scores = score_overlay(
            ov,
            tools,
            expected_tools=(expected_tools or {}).get(ov["id"]),
            observed_starts=(observed_starts or {}).get(ov["id"]),
        )
        rows.append({"overlay_id": ov["id"], "scores": scores, "failures": failures(scores, t)})
    n = len(rows)
    summary = {
        "overlays": n,
        "failed": sum(bool(r["failures"]) for r in rows),
        "grounding_rate": sum(r["scores"]["grounding_rate"] for r in rows) / n if n else 1.0,
        "within_tolerance_rate": (
            sum(r["scores"]["within_tolerance_rate"] for r in rows) / n if n else 1.0
        ),
        "cue_word_align_p95_ms": max(
            (r["scores"]["cue_word_align_p95_ms"] for r in rows), default=0.0
        ),
    }
    return {
        "passed": n > 0 and summary["failed"] == 0,
        "thresholds": asdict(t),
        "summary": summary,
        "rows": rows,
    }


def run_suite(
    crew: Any,
    tools: Tools,
    moments: list[dict[str, Any]] | None = None,
    *,
    lenses: tuple[str, ...] = ("casual", "analyst", "newcomer"),
    sides: tuple[str, ...] = ("home", "away", "neutral"),
) -> dict[str, Any]:
    """Run ``crew`` (a ``chalktalk_crew.Crew``) over each test moment and evaluate the output."""
    overlays: list[dict[str, Any]] = []
    expected: dict[str, list[str]] = {}
    for moment in moments if moments is not None else load_moments():
        produced = crew.run(moment["events"], lenses=lenses, sides=sides)
        if not produced:
            raise ValueError(f"moment {moment['id']!r} produced no overlay")
        for ov in produced:
            expected[ov["id"]] = moment.get("expect_tools", [])
        overlays.extend(produced)
    return evaluate(overlays, tools, expected_tools=expected)
