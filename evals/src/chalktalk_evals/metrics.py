"""Offline eval metrics over overlay contracts. Independent of the crew's own Verifier:
these re-derive every score from the overlay and a fresh tool client.

- claim grounding: every number spoken is the formatted value of a claim bound to a tool call;
- numeric tolerance: every claim value matches a re-run of its tool within its tolerance;
- cue timing: stroke start = cue ``offset_ms`` - ``lead_ms``; the cue sits on a word start; and,
  when the player reports observed stroke starts, the sync error against that expected start.
"""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Any, Protocol

NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")  # 0.42, or 0,42 in Spanish
DECIMAL_COMMA = {"es", "fr", "de", "it", "pt"}  # languages that speak 0,42


class Tools(Protocol):
    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


def spoken_form(value: Any, unit: str | None, lang: str | None = None) -> str:
    # Mirrors the crew's spoken format; kept here so evals do not trust crew code.
    if isinstance(value, bool | str):
        return str(value)
    if unit == "xG":
        text = f"{value:.2f}"
    elif unit == "m":
        text = f"{value:.1f}"
    else:
        return str(round(value))
    comma = (lang or "en").split("-")[0].lower() in DECIMAL_COMMA
    return text.replace(".", ",") if comma else text


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _rate(ok: int, total: int) -> float:
    return 1.0 if total == 0 else ok / total


def claim_grounding(overlay: dict[str, Any]) -> dict[str, float]:
    bound = [
        c for c in overlay["claims"] if c.get("tool_call", {}).get("name") and c["tool_call"]["id"]
    ]
    forms = {spoken_form(c["value"], c.get("unit"), overlay.get("lang")) for c in bound}
    numbers = NUMBER.findall(overlay["script"]["text"])
    grounded = sum(n in forms for n in numbers)
    return {
        "numbers": float(len(numbers)),
        "grounded_numbers": float(grounded),
        "grounding_rate": _rate(grounded, len(numbers)),
        "claims_with_tool_call": _rate(len(bound), len(overlay["claims"])),
    }


def numeric_tolerance(overlay: dict[str, Any], tools: Tools) -> dict[str, float]:
    within = numeric = 0
    errors: list[float] = []
    for claim in overlay["claims"]:
        call = claim["tool_call"]
        fresh = tools.call(call["name"], call["args"]).get("value")
        value, tol = claim["value"], claim.get("tolerance")
        if isinstance(value, int | float) and not isinstance(value, bool) and tol is not None:
            numeric += 1
            err = abs(float(value) - float(fresh))
            errors.append(err)
            within += err <= tol + 1e-9
    return {
        "numeric_claims": float(numeric),
        "within_tolerance_rate": _rate(within, numeric),
        "max_abs_error": max(errors, default=0.0),
    }


def cue_timing(
    overlay: dict[str, Any], observed_starts: dict[str, int] | None = None
) -> dict[str, float]:
    """Timing per stroke. ``observed_starts`` maps stroke id -> visible start (audio clock ms)."""
    cues = {c["cue_id"]: c["offset_ms"] for c in overlay["script"]["cues"]}
    word_starts = [w["offset_ms"] for w in overlay["script"].get("words") or []]
    missing = negative = 0
    align_errors: list[float] = []
    sync_errors: list[float] = []
    for stroke in overlay["strokes"]:
        offset = cues.get(stroke["cue_id"])
        if offset is None:
            missing += 1
            continue
        start = offset - stroke.get("lead_ms", 150)
        negative += start < 0
        if word_starts:
            align_errors.append(float(min(abs(offset - w) for w in word_starts)))
        if observed_starts and stroke["id"] in observed_starts:
            sync_errors.append(float(abs(observed_starts[stroke["id"]] - start)))
    n = len(overlay["strokes"])
    out = {
        "strokes": float(n),
        "cue_bound_rate": _rate(n - missing, n),
        "negative_starts": float(negative),
        "cue_word_align_median_ms": median(align_errors) if align_errors else 0.0,
        "cue_word_align_p95_ms": p95(align_errors),
    }
    if sync_errors:
        out["sync_median_ms"] = median(sync_errors)
        out["sync_p95_ms"] = p95(sync_errors)
    return out


def key_facts_coverage(overlay: dict[str, Any], expected_tools: list[str]) -> float:
    used = {c["tool_call"]["name"] for c in overlay["claims"]}
    return _rate(sum(t in used for t in expected_tools), len(expected_tools))
